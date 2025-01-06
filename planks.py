import random
import math
import time

class Plank:
    PICKUP_DISTANCE = 5
    HEALTH = 1000

    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def can_pickup(self, player_x, player_y, player_z):
        horizontal_distance = math.sqrt((self.x - player_x)**2 + (self.z - player_z)**2)
        vertical_distance = abs(self.y - player_y)
        return horizontal_distance < self.PICKUP_DISTANCE and vertical_distance < 3

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z
        }

class PlacedPlank:
    def __init__(self, x, y, z, rotation=0, is_wall=False):
        self.x = x
        self.y = y
        self.z = z
        self.rotation = rotation
        self.is_wall = is_wall
        self.health = 1000

    def take_damage(self, damage):
        self.health -= damage
        return self.health <= 0

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'rotation': self.rotation,
            'is_wall': self.is_wall,
            'health': self.health
        }

class PlankManager:
    MAX_PLANKS = 10
    SPAWN_INTERVAL = 15

    def __init__(self, map_size):
        self.planks = {}  # Подбираемые доски
        self.placed_planks = {}  # Установленные доски
        self.map_size = map_size
        self.next_plank_id = 0
        self.next_placed_id = 0
        self.walls = []
        self.last_spawn_time = 0
        self.planks_to_remove = set()  # Добавляем множество для хранения ID стен для удаления

    def set_walls(self, map_data):
        self.walls = [obj for obj in map_data if obj.get('texture') in ['brick', 'cobblestone']]

    def check_collision(self, x, z):
        for wall in self.walls:
            wall_x = wall['x']
            wall_z = wall['z']
            wall_scale_x = wall['scale_x']
            wall_scale_z = wall['scale_z']
            
            if abs(x - wall_x) < wall_scale_x/2 and abs(z - wall_z) < wall_scale_z/2:
                return True
        return False

    def spawn_plank(self):
        current_time = time.time()
        
        if current_time - self.last_spawn_time < self.SPAWN_INTERVAL:
            return

        if len(self.planks) >= self.MAX_PLANKS:
            oldest_id = min(self.planks.keys())
            del self.planks[oldest_id]

        for _ in range(20):
            x = random.uniform(-self.map_size*2 + 5, self.map_size*2 - 5)
            z = random.uniform(-self.map_size*2 + 5, self.map_size*2 - 5)
            
            if not self.check_collision(x, z):
                self.planks[self.next_plank_id] = Plank(x, 0, z)
                self.next_plank_id += 1
                self.last_spawn_time = current_time
                return

    def check_pickups(self, players):
        planks_to_remove = []
        
        for plank_id, plank in self.planks.items():
            for player in players.values():
                if player.is_alive and not player.is_ghost:
                    if plank.can_pickup(player.x, player.y, player.z):
                        player.planks_count += 1  # Увеличиваем количество досок у игрока
                        planks_to_remove.append(plank_id)
                        break

        for plank_id in planks_to_remove:
            del self.planks[plank_id]

    def place_plank(self, x, y, z, rotation, is_wall, player):
        if player.planks_count > 0:
            self.placed_planks[self.next_placed_id] = PlacedPlank(x, y, z, rotation, is_wall)
            self.next_placed_id += 1
            player.planks_count -= 1
            return True
        return False

    def update_placed_planks(self, zombies):
        # Удаляем сломанные стены
        for plank_id in self.planks_to_remove:
            if plank_id in self.placed_planks:
                del self.placed_planks[plank_id]
        self.planks_to_remove.clear()

        planks_to_remove = []
        
        for plank_id, plank in self.placed_planks.items():
            for zombie in zombies.values():
                if zombie.is_alive:
                    # Проверяем, находится ли зомби рядом с доской
                    dx = zombie.x - plank.x
                    dz = zombie.z - plank.z
                    distance = math.sqrt(dx*dx + dz*dz)
                    
                    if distance < zombie.DAMAGE_DISTANCE:
                        # Зомби атакует доску
                        if plank.take_damage(zombie.DAMAGE * zombie.damage_multiplier * 0.016):
                            planks_to_remove.append(plank_id)

        for plank_id in planks_to_remove:
            del self.placed_planks[plank_id]

    def to_dict(self):
        return {
            'pickups': {str(pid): p.to_dict() for pid, p in self.planks.items()},
            'placed': {str(pid): p.to_dict() for pid, p in self.placed_planks.items()}
        }
