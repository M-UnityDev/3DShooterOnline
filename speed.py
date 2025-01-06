import random
import math
import time

class SpeedBoost:
    COOLDOWN_REDUCTION = 0.25
    PICKUP_DISTANCE = 5  # Увеличиваем с 2 до 5

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

class SpeedBoostManager:
    MAX_BOOSTS = 5
    SPAWN_INTERVAL = 30  # Интервал появления бонусов в секундах

    def __init__(self, map_size):
        self.speed_boosts = {}
        self.map_size = map_size
        self.next_boost_id = 0
        self.walls = []
        self.last_spawn_time = 0

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

    def spawn_boost(self):
        current_time = time.time()
        
        if current_time - self.last_spawn_time < self.SPAWN_INTERVAL:
            return

        if len(self.speed_boosts) >= self.MAX_BOOSTS:
            # Удаляем самый старый бонус
            oldest_id = min(self.speed_boosts.keys())
            del self.speed_boosts[oldest_id]

        # Пытаемся найти подходящее место для спавна
        for _ in range(20):  # Максимум 20 попыток найти место
            x = random.uniform(-self.map_size*2 + 5, self.map_size*2 - 5)
            z = random.uniform(-self.map_size*2 + 5, self.map_size*2 - 5)
            
            if not self.check_collision(x, z):
                self.speed_boosts[self.next_boost_id] = SpeedBoost(x, 0, z)
                self.next_boost_id += 1
                self.last_spawn_time = current_time
                return

    def check_pickups(self, players):
        boosts_to_remove = []
        
        for boost_id, boost in self.speed_boosts.items():
            for player in players.values():
                if player.is_alive and not player.is_ghost:
                    if boost.can_pickup(player.x, player.y, player.z):
                        player.shoot_cooldown = max(0.1, player.shoot_cooldown - SpeedBoost.COOLDOWN_REDUCTION)
                        boosts_to_remove.append(boost_id)
                        break

        for boost_id in boosts_to_remove:
            del self.speed_boosts[boost_id]

    def to_dict(self):
        return {str(bid): b.to_dict() for bid, b in self.speed_boosts.items()}
