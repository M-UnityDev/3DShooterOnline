import socket
import json
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import time as py_time
import math
from collections import deque
import threading
import queue

# Константы
BULLET_SPEED = 30
MAX_BOUNCES = 3
SHOOT_COOLDOWN = 1.0
GRAVITY = 0.25
JUMP_POWER = 10
PLAYER_SPEED = 50
SPAWN_POSITION = Vec3(0, 50, 0)

# Создаем окно до подключения к серверу
app = Ursina(vsync=True,show_ursina_splash=True)
s = Sky()
# Создаем загрузочный экран
loading_text = Text(text='Загрузка...', origin=(0,0), scale=3)

# Создаем все необходимые объекты и переменные
other_players = {}
bullets = []
zombies = {}
last_shot_time = 0
medkits = {}
speed_boosts = {}
planks = {}
placed_planks = {}
preview_plank = None
planks_count_text = None
shoot_cooldown = 1.0
is_alive = True
player_health = 100
mouse_pressed = False
network_buffer = deque(maxlen=3)  # Буфер для последних 3 состояний
network_queue = queue.Queue()
game_state_queue = queue.Queue()
network_thread = None
should_run = True
last_network_update = 0
NETWORK_UPDATE_INTERVAL = 0.0005  # 20 обновлений в секунду
network_data = None  # Глобальная переменная для хранения последних полученных данных
network_lock = threading.Lock()  # Для безопасного доступа к network_data
client_socket = None
running = True
interpolated_zombies = {}  # Словарь для хранения интерполированных зомби
interpolated_players = {}  # Словарь для хранения интерполированных игроков

class Bullet(Entity):
    def __init__(self, position, direction, shooter_id=None):
        super().__init__(
            model='sphere',
            color=color.white,
            scale=0.3,
            position=position,
            collider='sphere'
        )
        self.direction = direction.normalized()
        self.bounces = 0
        self.damage = 20
        self.creation_time = py_time.time()
        self.lifetime = 10
        self.shooter_id = shooter_id

    def update(self):
        if py_time.time() - self.creation_time > self.lifetime:
            destroy(self)
            bullets.remove(self)
            return

        old_position = self.position
        self.position += self.direction * BULLET_SPEED * time.dt

        hit_info = raycast(
            old_position,
            self.direction,
            distance=BULLET_SPEED * time.dt,
            ignore=[self, player]
        )

        if hit_info.hit:
            hit_zombie = False
            for zid, zombie in zombies.items():
                if hit_info.entity == zombie:
                    hit_zombie = True
                    hit_data = {
                        'type': 'hit',
                        'target_id': int(zid),
                        'damage': self.damage
                    }
                    send_data(hit_data)
                    destroy(self)
                    bullets.remove(self)
                    return

            if not hit_zombie:
                if self.bounces >= MAX_BOUNCES:
                    destroy(self)
                    bullets.remove(self)
                    return

                normal = hit_info.normal
                if normal:
                    dot = self.direction.dot(normal)
                    self.direction = (self.direction - normal * 2 * dot).normalized()
                    self.position = hit_info.world_point + (normal * 0.1)
                    self.bounces += 1
                else:
                    destroy(self)
                    bullets.remove(self)

class InterpolatedZombie:
    def __init__(self, entity):
        self.entity = entity
        self.target_pos = entity.position
        self.start_pos = entity.position
        self.lerp_time = 0
        self.lerp_duration = 0.05
        self.velocity = Vec3(0, 0, 0)
        self.last_pos = entity.position
        self.last_update_time = py_time.time()
        self.health = 60
        self.is_alive = True
        self.smooth_pos = entity.position  # Добавляем сглаженную позицию

    def take_damage(self, damage):
        self.health -= damage
        if self.health <= 0 and self.is_alive:
            self.is_alive = False
            return True
        return False

    def update(self, dt):
        if not self.is_alive:
            return

        current_time = py_time.time()
        
        if current_time - self.last_update_time > 0:
            self.velocity = (self.target_pos - self.last_pos) / (current_time - self.last_update_time)
            predicted_pos = self.target_pos + self.velocity * dt * 5
        else:
            predicted_pos = self.target_pos
        
        # Сглаживаем движение
        self.smooth_pos = Vec3(
            lerp(self.smooth_pos.x, predicted_pos.x, dt * 10),
            lerp(self.smooth_pos.y, predicted_pos.y, dt * 10),
            lerp(self.smooth_pos.z, predicted_pos.z, dt * 10)
        )
        
        self.entity.position = self.smooth_pos

    def set_target(self, new_pos):
        self.last_pos = self.target_pos
        self.start_pos = self.entity.position
        self.target_pos = new_pos
        self.lerp_time = 0
        self.last_update_time = py_time.time()

class InterpolatedPlayer:
    def __init__(self, entity):
        self.entity = entity
        self.target_pos = entity.position
        self.smooth_pos = entity.position
        self.velocity = Vec3(0, 0, 0)
        self.last_pos = entity.position
        self.last_update_time = py_time.time()

    def update(self, dt):
        current_time = py_time.time()
        
        if current_time - self.last_update_time > 0:
            self.velocity = (self.target_pos - self.last_pos) / (current_time - self.last_update_time)
            predicted_pos = self.target_pos + self.velocity * dt * 5
        else:
            predicted_pos = self.target_pos
        
        # Сглаживаем движение
        self.smooth_pos = Vec3(
            lerp(self.smooth_pos.x, predicted_pos.x, dt * 10),
            lerp(self.smooth_pos.y, predicted_pos.y, dt * 10),
            lerp(self.smooth_pos.z, predicted_pos.z, dt * 10)
        )
        
        self.entity.position = self.smooth_pos

    def set_target(self, new_pos):
        self.last_pos = self.target_pos
        self.target_pos = new_pos
        self.last_update_time = py_time.time()

def create_zombie():
    zombie = Entity(
        model='sphere',
        texture='zfront',  # Базовая текстура для всех сторон
        scale=(1, 2, 1),
        collider='box'
    )
    
    # Добавляем вторую текстуру для передней стороны
    zombie.texture_front = 'zface'  # Текстура лица для передней стороны
    
    return zombie

def create_other_player(id):
    return Entity(
        model='box',
        color=color.blue,
        scale=(1, 2, 1),
        collider='box'
    )

def create_medkit():
    return Entity(
        model='cube',
        texture='apteka',  # Используем текстуру apteka.png
        scale=(0.5, 0.5, 0.5),
        collider='box'
    )

def create_speed_boost():
    return Entity(
        model='cube',
        texture='speed',  # Используем текстуру speed.png
        scale=(0.5, 0.5, 0.5),
        collider='box'
    )

def create_plank():
    return Entity(
        model='cube',
        texture='planks',  # Используем текстуру planks.png
        scale=(4, 0.5, 2),
        collider='box'
    )

# Создаем все функции (create_zombie, create_other_player и т.д.)

def send_data(data):
    try:
        message = json.dumps(data).encode()
        message_length = len(message)
        header = str(message_length).encode().ljust(10)
        client_socket.send(header + message)
    except Exception as e:
        print(f"Ошибка при отправке данных: {e}")

def receive_data():
    try:
        # Получаем заголовок
        header = b""
        while len(header) < 10:
            chunk = client_socket.recv(10 - len(header))
            if not chunk:
                return None
            header += chunk
        
        # Получаем длину сообщения
        message_length = int(header.decode().strip())
        
        # Получаем само сообщение
        message = b""
        while len(message) < message_length:
            chunk = client_socket.recv(min(message_length - len(message), 4096))
            if not chunk:
                return None
            message += chunk
        
        return json.loads(message.decode())
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None

def network_loop():
    global network_data, running
    while running:
        try:
            # Отправляем позицию и направление взгляда
            with network_lock:
                send_data({
                    'x': player.x,
                    'y': player.y,
                    'z': player.z,
                    'shooting': held_keys['left mouse'] and py_time.time() - last_shot_time < 0.1,
                    'shoot_dir_x': camera.forward.x,
                    'shoot_dir_y': camera.forward.y,
                    'shoot_dir_z': camera.forward.z
                })

            # Получаем данные
            data = receive_data()
            if data:
                with network_lock:
                    global network_data
                    network_data = data
            else:
                print("Потеряно соединение с сервером")
                running = False
                break

            # Небольшая задержка
            py_time.sleep(0.05)
        except Exception as e:
            print(f"Ошибка сети: {e}")
            running = False
            break

def start_network_thread():
    global network_thread, should_run
    should_run = True
    network_thread = threading.Thread(target=network_loop)
    network_thread.daemon = True
    network_thread.start()

def stop_network_thread():
    global should_run
    should_run = False
    if network_thread:
        network_thread.join()

def initialize_game():
    global player_id, map_data, client_socket, player, health_text, planks_count_text, is_alive, player_health

    try:
        # Подключаемся к серверу
        client_socket = socket.socket()
        client_socket.connect(('127.0.0.1', 21491))

        # Получаем начальные данные
        data = receive_data()
        if not data or 'id' not in data or 'map' not in data:
            raise Exception("Неверный формат начальных данных")

        player_id = data['id']
        map_data = data['map']

        # Создаем карту
        for platform_data in map_data:
            Entity(
                model='cube',
                position=(platform_data['x'], platform_data['y'], platform_data['z']),
                scale=(platform_data['scale_x'], platform_data['scale_y'], platform_data['scale_z']),
                rotation_y=platform_data['rotation_y'],
                texture=platform_data['texture'],
                collider='box'
            )

        # Создаем игрока
        player = FirstPersonController()
        player.speed = PLAYER_SPEED
        player.position = SPAWN_POSITION
        player.collision = True
        player.gravity = GRAVITY
        player.jump_height = JUMP_POWER
        player.jump_duration = 0.25
        player.jump_up_duration = 0.25
        player.fall_after = 0.25

        # Создаем интерфейс
        health_text = Text(text='HP: 100', position=(-0.6, 0.45), scale=2, color=color.rgb(255, 50, 50))
        planks_count_text = Text(text='Доски: 0', position=(-0.6, 0.4), scale=2)

        # Инициализируем состояние игрока
        is_alive = True
        player_health = 100

        # Удаляем загрузочный экран
        destroy(loading_text)

        # Запускаем сетевой поток
        network_thread = threading.Thread(target=network_loop)
        network_thread.daemon = True
        network_thread.start()

        return True

    except Exception as e:
        print(f"Ошибка при инициализации: {e}")
        return False

def update():
    global last_shot_time, player_health, is_alive, shoot_cooldown, preview_plank, player_data, mouse_pressed, player

    current_time = py_time.time()

    # Получаем сетевые данные в начале функции
    current_network_data = None
    with network_lock:
        current_network_data = network_data

    # Обновляем интерполяцию всех зомби
    for zombie in interpolated_zombies.values():
        zombie.update(time.dt)

    # Обновляем интерполяцию других игроков
    if current_network_data is not None and 'players' in current_network_data:
        players_data = current_network_data['players']
        
        # Сначала удаляем отключившихся игроков
        for pid in list(other_players.keys()):
            if pid not in players_data or pid == str(player_id):
                if pid in interpolated_players:  # Добавляем проверку
                    del interpolated_players[pid]
                destroy(other_players[pid])
                del other_players[pid]
        
        # Затем обновляем или создаем других игроков
        for pid, pdata in players_data.items():
            if pid != str(player_id):
                try:
                    if pid not in other_players:
                        other_players[pid] = create_other_player(pid)
                        interpolated_players[pid] = InterpolatedPlayer(other_players[pid])
                    
                    if pid in interpolated_players and pid in other_players:  # Проверяем наличие обоих объектов
                        new_pos = Vec3(pdata['x'], pdata['y'], pdata['z'])
                        interpolated_players[pid].set_target(new_pos)
                        
                        if not pdata['is_alive']:
                            other_players[pid].color = color.rgba(0, 0, 1, 0.5)
                        else:
                            other_players[pid].color = color.blue
                except Exception as e:
                    print(f"Ошибка при обновлении игрока {pid}: {e}")
                    # Если что-то пошло не так, удаляем оба объекта
                    if pid in interpolated_players:
                        del interpolated_players[pid]
                    if pid in other_players:
                        destroy(other_players[pid])
                        del other_players[pid]

    # Обновляем интерполяцию только для существующих игроков
    for pid in list(interpolated_players.keys()):
        if pid in other_players:  # Проверяем, что игрок все еще существует
            try:
                interpolated_players[pid].update(time.dt)
            except Exception as e:
                print(f"Ошибка при интерполяции игрока {pid}: {e}")
                del interpolated_players[pid]
                if pid in other_players:
                    destroy(other_players[pid])
                    del other_players[pid]

    # Инициализируем player_data в начале функции
    player_data = {'planks_count': 0}

    # Обработка стрельбы
    if (is_alive and held_keys['left mouse'] and current_time - last_shot_time >= shoot_cooldown 
        and not (held_keys['f'] or held_keys['g'])):
        bullet_pos = camera.world_position + (camera.forward * 2)
        bullet = Bullet(bullet_pos, camera.forward, player_id)
        bullets.append(bullet)
        last_shot_time = current_time

        send_data({
            'type': 'shoot',
            'bullet_pos_x': bullet_pos.x,
            'bullet_pos_y': bullet_pos.y,
            'bullet_pos_z': bullet_pos.z,
            'bullet_dir_x': camera.forward.x,
            'bullet_dir_y': camera.forward.y,
            'bullet_dir_z': camera.forward.z
        })

    if not is_alive:
        player.gravity = 0
        player.speed = 20
        player.collision = False
        
        if held_keys['space']:
            player.y += player.speed * time.dt
        if held_keys['shift']:
            player.y -= player.speed * time.dt
        return

    # Обработка сетевых данных
    if current_network_data is not None:
        # Обработка зомби
        if 'zombies' in current_network_data:
            zombies_data = current_network_data['zombies']
            # Удаляем зомби, которых больше нет
            for zid in list(zombies.keys()):
                if zid not in zombies_data or not zombies_data[zid]['is_alive']:
                    if zid in interpolated_zombies:
                        del interpolated_zombies[zid]
                    destroy(zombies[zid])
                    del zombies[zid]
            # Обновляем или создаем зомби
            for zid, zdata in zombies_data.items():
                if zdata['is_alive']:
                    new_pos = Vec3(zdata['x'], zdata['y'], zdata['z'])
                    if zid not in zombies:
                        zombies[zid] = create_zombie()
                        interpolated_zombies[zid] = InterpolatedZombie(zombies[zid])
                        interpolated_zombies[zid].set_target(new_pos)
                    else:
                        interpolated_zombies[zid].set_target(new_pos)
                        # Поворачиваем зомби в сторону игрока
                        zombies[zid].look_at(Vec3(player.x, zombies[zid].y, player.z))
                    zombies[zid].scale = (1, zdata.get('scale', 2), 1)

        # Обработка аптечек
        if 'medkits' in current_network_data:
            medkits_data = current_network_data['medkits']
            # Удаляем отсутствующие аптечки
            for mid in list(medkits.keys()):
                if mid not in medkits_data:
                    destroy(medkits[mid])
                    del medkits[mid]
            # Обновляем или создаем аптечки
            for mid, mdata in medkits_data.items():
                if mid not in medkits:
                    medkits[mid] = create_medkit()
                medkits[mid].position = (mdata['x'], mdata['y'], mdata['z'])

        # Обработка бустов
        if 'speed_boosts' in current_network_data:
            speed_boosts_data = current_network_data['speed_boosts']
            # Удаляем отсутствующие бусты
            for bid in list(speed_boosts.keys()):
                if bid not in speed_boosts_data:
                    destroy(speed_boosts[bid])
                    del speed_boosts[bid]
            # Обновляем или создаем бусты
            for bid, bdata in speed_boosts_data.items():
                if bid not in speed_boosts:
                    speed_boosts[bid] = create_speed_boost()
                speed_boosts[bid].position = (bdata['x'], bdata['y'], bdata['z'])

        # Обработка досок
        if 'planks' in current_network_data:
            planks_data = current_network_data['planks']
            # Обработка подбираемых досок
            pickups_data = planks_data.get('pickups', {})
            # Удаляем отсутствующие доски
            for pid in list(planks.keys()):
                if pid not in pickups_data:
                    destroy(planks[pid])
                    del planks[pid]
            # Обновляем или создаем доски
            for pid, pdata in pickups_data.items():
                if pid not in planks:
                    planks[pid] = create_plank()
                planks[pid].position = (pdata['x'], pdata['y'], pdata['z'])

            # Обработка размещенных досок
            placed_data = planks_data.get('placed', {})
            # Удаляем отсутствующие размещенные доски
            for pid in list(placed_planks.keys()):
                if pid not in placed_data:
                    destroy(placed_planks[pid])
                    del placed_planks[pid]
            # Обновляем или создаем размещенные доски
            for pid, pdata in placed_data.items():
                if pid not in placed_planks:
                    placed_planks[pid] = create_plank()
                    if pdata['is_wall']:
                        placed_planks[pid].scale = (2, 4, 0.5)
                placed_planks[pid].position = (pdata['x'], pdata['y'], pdata['z'])
                placed_planks[pid].rotation_y = pdata['rotation']

        # Обработка игроков
        if 'players' in current_network_data:
            players_data = current_network_data['players']
            # Обработка данных текущего игрока
            if str(player_id) in players_data:
                player_data = players_data[str(player_id)]
                player_health = int(player_data['health'])
                shoot_cooldown = player_data['shoot_cooldown']
                health_text.text = f'HP: {player_health}'
                planks_count_text.text = f'Доски: {player_data["planks_count"]}'

                # Проверяем смерть игрока
                if not player_data['is_alive'] and is_alive:
                    is_alive = False
                    player.gravity = 0
                    player.speed = 10
                    player.collision = False
                    player.model = None
                    player.collider = None
                    Text(text='ВЫ УМЕРЛИ', origin=(0,0), scale=3, color=color.red)

    # Добавим обработку удаления стен (перед обработкой размещения досок)
    if held_keys['q']:
        if not hasattr(update, 'last_remove_time'):
            update.last_remove_time = 0
        
        current_time = py_time.time()
        if current_time - update.last_remove_time >= 0.5:  # Задержка между удалениями
            hit_info = raycast(camera.world_position, camera.forward, distance=10)
            if hit_info.hit:
                # Проверяем, попали ли мы в размещенную доску
                for pid, plank in placed_planks.items():
                    if hit_info.entity == plank:
                        try:
                            send_data({
                                'type': 'remove_plank',
                                'plank_id': str(pid)  # Преобразуем в строку
                            })
                            update.last_remove_time = current_time
                        except Exception as e:
                            print(f"Ошибка при отправке запроса на удаление доски: {e}")
                        break

    # Обработка размещения досок
    if held_keys['f'] or held_keys['g']:
        if not preview_plank:
            preview_plank = Entity(
                model='cube',
                texture='planks',  # Добавляем текстуру для превью
                color=color.rgba(255, 255, 255, 0.5),  # Делаем полупрозрачным
                scale=(4, 0.5, 2) if held_keys['f'] else (2, 4, 0.5)
            )
        
        # Позиционируем доску относительно игрока
        if held_keys['g']:  # Режим стены
            # Получаем направление взгляда игрока
            forward = camera.forward
            right = camera.right
            
            # Вычисляем позицию на основе направления взгляда
            hit_info = raycast(camera.world_position, camera.forward, distance=10)
            target_y = player.y + camera.forward.y * 5  # Поднимаем/опускаем стену в зависимости от взгляда
            
            if hit_info.hit:
                # Если луч попал в объект, размещаем стену перед ним
                target_pos = hit_info.world_point - forward * 0.5
            else:
                # Если луч не попал, размещаем на фиксированном расстоянии
                target_pos = player.position + forward * 3
            
            # Улучшенное центрирование стены
            target_pos += right * 0.20  # Смещаем вправо
            target_pos.y = target_y - -2  # Опускаем немного ниже
            
            preview_plank.position = target_pos
            
            # Вычисляем угол поворота на основе направления взгляда
            forward.y = 0  # Обнуляем вертикальную составляющую для расчета угла
            angle = math.degrees(math.atan2(forward.x, forward.z))
            preview_plank.rotation_y = angle
            
        else:  # Режим пола
            hit_info = raycast(camera.world_position, camera.forward, distance=10)
            if hit_info.hit:
                # Позиционируем пол с учетом высоты взгляда
                target_pos = hit_info.world_point
                target_pos.y += 0.25  # Немного поднимаем над поверхностью
                preview_plank.position = target_pos
                
                # Поворачиваем пол в направлении игрока
                direction = Vec3(player.x, 0, player.z) - Vec3(preview_plank.x, 0, preview_plank.z)
                angle = math.degrees(math.atan2(direction.x, direction.z))
                preview_plank.rotation_y = angle
        
        # Размещение доски только при новом нажатии кнопки мыши
        if held_keys['left mouse']:
            if not mouse_pressed and player_data.get('planks_count', 0) > 0:
                send_data({
                    'type': 'place_plank',
                    'x': preview_plank.x,
                    'y': preview_plank.y,
                    'z': preview_plank.z,
                    'rotation': preview_plank.rotation_y,
                    'is_wall': held_keys['g']
                })
            mouse_pressed = True
        else:
            mouse_pressed = False  # Сбрасываем флаг, когда кнопка отпущена
    else:
        if preview_plank:
            destroy(preview_plank)
            preview_plank = None
        mouse_pressed = False  # Сбрасываем флаг при выходе из режима строительства

def on_quit():
    global running
    running = False
    if client_socket:
        client_socket.close()

# Регистрируем обработчик выхода
from atexit import register
register(on_quit)

# Инициализируем игру
if initialize_game():
    app.run()
else:
    print("Не удалось инициализировать игру")
    exit(1)