import socket
import json
import threading
import random
import time
import urllib.request  # Используем urllib вместо requests, так как он встроен в Python
from map_generator import generate_map
from player import Player
from zombie import ZombieManager
from apteka import MedkitManager
from speed import SpeedBoostManager
from planks import PlankManager

def get_external_ip():
    try:
        external_ip = urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
        return external_ip
    except:
        return "Не удалось получить внешний IP"

def get_local_ip():
    try:
        # Получаем локальный IP, создавая временное подключение
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

SPAWN_POSITION = (0, 5, 0)
MAP_SIZE = 40

class GameServer:
    def __init__(self, port=21491):
        # Получаем и выводим информацию о подключении перед инициализацией сервера
        self.port = port
        local_ip = get_local_ip()
        external_ip = get_external_ip()
        
        print("\n=== Информация о сервере ===")
        print(f"Порт: {self.port}")
        print(f"Локальный IP: {local_ip}")
        print(f"Внешний IP: {external_ip}")
        print("\nДля подключения по локальной сети используйте:")
        print(f"IP: {local_ip}, Порт: {self.port}")
        print("\nДля подключения из интернета используйте:")
        print(f"IP: {external_ip}, Порт: {self.port}")
        print("(Убедитесь, что порт проброшен на роутере)")
        print("============================\n")

        # Инициализация остальных компонентов
        self.players = {}
        self.zombie_manager = ZombieManager(MAP_SIZE)
        self.players_lock = threading.Lock()
        self.zombies_lock = threading.Lock()
        
        self.map_data = generate_map(MAP_SIZE)
        self.map_json = json.dumps(self.map_data)
        self.zombie_manager.set_walls(self.map_data)
        
        self.server_socket = socket.socket()
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(10)
        
        self.next_player_id = 0
        self.medkit_manager = MedkitManager(MAP_SIZE)
        self.medkit_manager.set_walls(self.map_data)
        self.speed_boost_manager = SpeedBoostManager(MAP_SIZE)
        self.speed_boost_manager.set_walls(self.map_data)
        self.plank_manager = PlankManager(MAP_SIZE)
        self.plank_manager.set_walls(self.map_data)
        self.zombie_manager.set_plank_manager(self.plank_manager)

    def reset_game(self):
        with self.zombies_lock:
            self.zombie_manager = ZombieManager(MAP_SIZE)
            self.zombie_manager.set_walls(self.map_data)
            self.zombie_manager.set_plank_manager(self.plank_manager)
            print("Игра сброшена: все зомби удалены")

    def check_active_players(self):
        with self.players_lock:
            # Проверяем, есть ли живые игроки
            alive_players = sum(1 for p in self.players.values() if p.is_alive)
            total_players = len(self.players)
            
            if total_players == 0:
                # Если игроков нет, сбрасываем игру
                self.reset_game()
                time.sleep(5)  # Задержка 5 секунд
                return False
            elif total_players == 1 and alive_players == 0:
                # Если есть только один игрок и он мертв
                return False
            return True

    def spawn_zombies(self):
        while True:
            try:
                # Проверяем состояние игроков
                if self.check_active_players():
                    with self.zombies_lock:
                        x = random.uniform(-MAP_SIZE*2 + 5, MAP_SIZE*2 - 5)
                        z = random.uniform(-MAP_SIZE*2 + 5, MAP_SIZE*2 - 5)
                        zombie_id = self.zombie_manager.spawn_zombie(x, 0, z)
                        if zombie_id is not None:
                            print(f"Зомби {zombie_id} создан на позиции ({x}, 0, {z})")
                time.sleep(random.uniform(5, 10))  # Перенесли sleep сюда
            except Exception as e:
                print(f"Ошибка при создании зомби: {e}")

    def update_zombies(self):
        with self.zombies_lock, self.players_lock:
            for zombie_id, zombie in self.zombie_manager.zombies.items():
                if not zombie.is_alive:
                    continue

                # Если у зомби нет цели или цель мертва, выбираем новую
                if (zombie.target_player_id is None or 
                    zombie.target_player_id not in self.players or 
                    not self.players[zombie.target_player_id].is_alive):
                    
                    # Находим ближайшего живого игрока
                    min_dist = float('inf')
                    closest_player_id = None
                    
                    for pid, player in self.players.items():
                        if player.is_alive:
                            dist = ((zombie.x - player.x) ** 2 + 
                                   (zombie.y - player.y) ** 2 + 
                                   (zombie.z - player.z) ** 2) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                closest_player_id = pid
                    
                    zombie.target_player_id = closest_player_id
                    print(f"Зомби {zombie_id} выбрал цель игрока {closest_player_id}")

                # Двигаем зомби к цели
                if zombie.target_player_id is not None:
                    zombie.move_towards_nearest_player(self.players, self.walls)
                    print(f"Зомби {zombie_id} перемещается к цели {zombie.target_player_id}")
                    
            # Отправляем обновленные позиции зомби клиентам
            self.broadcast_zombie_updates()

    def broadcast_zombie_updates(self):
        game_state = {
            'zombies': self.zombie_manager.to_dict(),
            # Другие данные игры...
        }
        for player_id, player in self.players.items():
            try:
                self.send_data(player.conn, game_state)
            except Exception as e:
                print(f"Ошибка при отправке данных игроку {player_id}: {e}")

    def send_map_data(self, conn):
        try:
            # Отправляем размер данных карты
            conn.send(str(len(self.map_json)).encode())
            
            # Разбиваем карту на чанки и отправляем
            for i in range(0, len(self.map_json), 1024):
                chunk = self.map_json[i:i+1024]
                conn.send(chunk.encode())
            
            # Отправляем маркер конца
            conn.send(b"END")
        except Exception as e:
            print(f"Ошибка при отправке карты: {e}")

    def send_data(self, conn, data):
        try:
            message = json.dumps(data).encode()
            message_length = len(message)
            header = str(message_length).encode().ljust(10)
            conn.send(header + message)
        except Exception as e:
            print(f"Ошибка при отправке данных: {e}")
            raise e

    def receive_data(self, conn):
        try:
            header = conn.recv(10).decode().strip()
            if not header:
                return None
            
            message_length = int(header)
            
            message = b""
            while len(message) < message_length:
                chunk = conn.recv(min(message_length - len(message), 1024))
                if not chunk:
                    return None
                message += chunk
            
            return json.loads(message.decode())
        except Exception as e:
            print(f"Ошибка при получении данных: {e}")
            return None

    def handle_client(self, conn, addr):
        player_id = self.next_player_id
        self.next_player_id += 1
        
        print(f'Подключился игрок {player_id} с адреса {addr}')
        
        try:
            # Отправляем ID и карту в одном сообщении
            initial_data = {
                'id': player_id,
                'map': self.map_data
            }
            self.send_data(conn, initial_data)
            
            # Создаем игрока
            with self.players_lock:
                self.players[player_id] = Player(*SPAWN_POSITION)
                self.players[player_id].conn = conn  # Добавляем связь с соединением
            
            while True:
                try:
                    player_data = self.receive_data(conn)
                    if not player_data:
                        break
                    
                    if 'type' in player_data:
                        if player_data['type'] == 'hit':
                            zombie_id = int(player_data['target_id'])
                            damage = player_data['damage']
                            with self.zombies_lock:
                                zombie = self.zombie_manager.get_zombie(zombie_id)
                                if zombie:
                                    was_alive = zombie.is_alive
                                    zombie.take_damage(damage)
                                    if was_alive and not zombie.is_alive:
                                        with self.players_lock:
                                            self.players[player_id].add_kill()
                                    print(f"Зомби {zombie_id} получил {damage} урона. HP: {zombie.health}")
                                    self.send_data(conn, {
                                        "hit_confirmed": True,
                                        "zombie_id": zombie_id,
                                        "health": zombie.health
                                    })
                        elif player_data['type'] == 'place_plank':
                            with self.players_lock:
                                if self.plank_manager.place_plank(
                                    player_data['x'],
                                    player_data['y'],
                                    player_data['z'],
                                    player_data['rotation'],
                                    player_data['is_wall'],
                                    self.players[player_id]
                                ):
                                    response = {"plank_placed": True}
                                else:
                                    response = {"plank_placed": False}
                                self.send_data(conn, response)
                        elif player_data['type'] == 'remove_plank':
                            try:
                                plank_id = str(player_data['plank_id'])  # Убедимся, что ID в строковом формате
                                with self.players_lock:
                                    if plank_id in self.plank_manager.placed_planks:
                                        # Возвращаем доску игроку
                                        self.players[player_id].planks_count += 1
                                        # Удаляем доску
                                        del self.plank_manager.placed_planks[plank_id]
                                        self.send_data(conn, {"plank_removed": True})
                                    else:
                                        self.send_data(conn, {"plank_removed": False})
                            except Exception as e:
                                print(f"Ошибка при удалении доски: {e}")
                                self.send_data(conn, {"plank_removed": False, "error": str(e)})
                    else:
                        # Обновляем позицию игрока
                        with self.players_lock:
                            if self.players[player_id].is_alive:
                                self.players[player_id].set_position(
                                    player_data['x'],
                                    player_data['y'],
                                    player_data['z']
                                )
                            
                            # Отправляем только необходимые данные
                            game_state = {
                                'players': {
                                    str(pid): {
                                        'x': p.x,
                                        'y': p.y,
                                        'z': p.z,
                                        'health': p.health,
                                        'is_alive': p.is_alive,
                                        'shoot_cooldown': p.shoot_cooldown,
                                        'planks_count': p.planks_count
                                    } for pid, p in self.players.items()
                                },
                                'zombies': {
                                    str(zid): {
                                        'x': z.x,
                                        'y': z.y,
                                        'z': z.z,
                                        'is_alive': z.is_alive,
                                        'scale': z.scale
                                    } for zid, z in self.zombie_manager.zombies.items()
                                },
                                'medkits': self.medkit_manager.to_dict(),
                                'speed_boosts': self.speed_boost_manager.to_dict(),
                                'planks': self.plank_manager.to_dict()
                            }
                            
                            self.send_data(conn, game_state)
        
                except Exception as e:
                    print(f"Ошибка обработки клиента: {e}")
                    break
        
        finally:
            with self.players_lock:
                if player_id in self.players:
                    del self.players[player_id]
            conn.close()
            print(f'Игрок {player_id} отключился')

    def update_medkits(self):
        while True:
            try:
                if self.check_active_players():
                    with self.players_lock:
                        self.medkit_manager.spawn_medkit()
                        self.medkit_manager.check_pickups(self.players)
                time.sleep(1)  # Проверяем каждую секунду
            except Exception as e:
                print(f"Ошибка при обновлении аптечек: {e}")

    def update_speed_boosts(self):
        while True:
            try:
                if self.check_active_players():
                    with self.players_lock:
                        self.speed_boost_manager.spawn_boost()
                        self.speed_boost_manager.check_pickups(self.players)
                time.sleep(1)
            except Exception as e:
                print(f"Ошибка при обновлении бонусов скорострельности: {e}")

    def update_planks(self):
        while True:
            try:
                if self.check_active_players():
                    with self.players_lock:
                        self.plank_manager.spawn_plank()
                        self.plank_manager.check_pickups(self.players)
                        self.plank_manager.update_placed_planks(self.zombie_manager.zombies)
                time.sleep(1)
            except Exception as e:
                print(f"Ошибка при обновлении досок: {e}")

    def run(self):
        # Запускаем потоки для зомби
        zombie_spawn_thread = threading.Thread(target=self.spawn_zombies)
        zombie_spawn_thread.daemon = True
        zombie_spawn_thread.start()

        zombie_update_thread = threading.Thread(target=self.update_zombies)
        zombie_update_thread.daemon = True
        zombie_update_thread.start()

        # Добавить потоки для аптечек, бонусов и досок
        medkit_thread = threading.Thread(target=self.update_medkits)
        medkit_thread.daemon = True
        medkit_thread.start()

        speed_boost_thread = threading.Thread(target=self.update_speed_boosts)
        speed_boost_thread.daemon = True
        speed_boost_thread.start()

        plank_thread = threading.Thread(target=self.update_planks)
        plank_thread.daemon = True
        plank_thread.start()

        print("Сервер запущен и ожидает подключений...")
        
        while True:
            try:
                conn, addr = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                print(f"Ошибка при подключении клиента: {e}")

if __name__ == "__main__":
    server = GameServer(port=21491)  # Используем порт 21491
    server.run()

