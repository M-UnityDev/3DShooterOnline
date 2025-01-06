import math

class Zombie:
    HEALTH = 60
    SPEED = 6
    DAMAGE = 10
    DAMAGE_DISTANCE = 2
    MERGE_DISTANCE = 3
    BASE_SCALE = 2
    WALL_DETECTION_MARGIN = 1.0  # Уменьшаем отступ
    COLLISION_RADIUS = 0.5  # Базовый радиус коллизии зомби

    def __init__(self, x, y, z):
        self.x = x
        self.y = 0
        self.z = z
        self.health = self.HEALTH
        self.is_alive = True
        self.last_position = (x, z)
        self.scale = self.BASE_SCALE
        self.damage_multiplier = 1
        self.speed_bonus = 0

    def take_damage(self, damage):
        self.health -= damage
        if self.health <= 0:
            self.health = 0
            self.is_alive = False
        return self.is_alive

    def merge_with(self, other_zombie):
        total_health = self.health + other_zombie.health
        self.health = total_health
        
        # Увеличиваем размер пропорционально здоровью
        self.scale = self.BASE_SCALE * (1 + (total_health / self.HEALTH - 1) * 0.5)
        
        # Увеличиваем урон пропорционально здоровью
        self.damage_multiplier = total_health / self.HEALTH
        
        # Добавляем скорость
        self.speed_bonus += 0.1
        
        # Обновляем позицию
        self.x = (self.x + other_zombie.x) / 2
        self.z = (self.z + other_zombie.z) / 2
        
        return True

    def check_collision(self, new_x, new_z, walls):
        # Используем фиксированный радиус коллизии
        zombie_radius = self.COLLISION_RADIUS
        
        # Проверка коллизий со стенами
        for wall in walls:
            wall_x = wall['x']
            wall_z = wall['z']
            wall_scale_x = wall['scale_x'] + self.WALL_DETECTION_MARGIN
            wall_scale_z = wall['scale_z'] + self.WALL_DETECTION_MARGIN
            wall_rotation = wall['rotation_y']
            
            if wall_rotation != 0:
                dx = new_x - wall_x
                dz = new_z - wall_z
                angle = math.radians(wall_rotation)
                rotated_x = dx * math.cos(angle) + dz * math.sin(angle)
                rotated_z = -dx * math.sin(angle) + dz * math.cos(angle)
                
                if abs(rotated_x) < (wall_scale_x/2 + zombie_radius) and \
                   abs(rotated_z) < (wall_scale_z/2 + zombie_radius):
                    return True
            else:
                if abs(new_x - wall_x) < (wall_scale_x/2 + zombie_radius) and \
                   abs(new_z - wall_z) < (wall_scale_z/2 + zombie_radius):
                    return True

        # Проверка коллизий с размещенными досками
        if hasattr(self, 'manager') and self.manager.plank_manager:
            for plank in self.manager.plank_manager.placed_planks.values():
                if plank.is_wall:
                    # Для вертикальных досок
                    dx = new_x - plank.x
                    dz = new_z - plank.z
                    angle = math.radians(plank.rotation)
                    rotated_x = dx * math.cos(angle) + dz * math.sin(angle)
                    rotated_z = -dx * math.sin(angle) + dz * math.cos(angle)
                    
                    if abs(rotated_x) < (2/2 + zombie_radius) and \
                       abs(rotated_z) < (0.5/2 + zombie_radius):
                        return True
                else:
                    # Для горизонтальных досок
                    if abs(new_x - plank.x) < (4/2 + zombie_radius) and \
                       abs(new_z - plank.z) < (2/2 + zombie_radius):
                        return True
        
        return False

    def move_towards_nearest_player(self, players, walls):
        nearest_player = None
        min_distance = float('inf')
        
        for player in players.values():
            if player.is_alive and not player.is_ghost:
                dx = self.x - player.x
                dz = self.z - player.z
                distance = (dx * dx + dz * dz) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    nearest_player = player

        if nearest_player:
            dx = nearest_player.x - self.x
            dz = nearest_player.z - self.z
            distance = (dx * dx + dz * dz) ** 0.5
            
            if distance > 0:
                current_speed = (self.SPEED + self.speed_bonus) * 0.016
                move_x = (dx / distance) * current_speed
                move_z = (dz / distance) * current_speed
                
                # Пробуем сначала диагональное движение
                new_x = self.x + move_x
                new_z = self.z + move_z
                
                # Проверяем коллизии со стенами и досками
                if not self.check_collision(new_x, new_z, walls):
                    self.x = new_x
                    self.z = new_z
                    self.last_position = (new_x, new_z)
                else:
                    # Если не можем пройти, проверяем наличие стен для атаки
                    if hasattr(self, 'manager') and self.manager.plank_manager:
                        for plank_id, plank in self.manager.plank_manager.placed_planks.items():
                            dx_plank = self.x - plank.x
                            dz_plank = self.z - plank.z
                            distance_to_plank = math.sqrt(dx_plank**2 + dz_plank**2)
                            
                            if distance_to_plank < self.DAMAGE_DISTANCE:
                                # Атакуем стену
                                if plank.take_damage(self.DAMAGE * self.damage_multiplier * 0.016):
                                    # Если стена разрушена, добавляем её ID для удаления
                                    self.manager.plank_manager.planks_to_remove.add(plank_id)
                                return True

                    # Если не получилось пройти и нет стен для атаки, пробуем двигаться по одной оси
                    if not self.check_collision(new_x, self.z, walls):
                        self.x = new_x
                    elif not self.check_collision(self.x, new_z, walls):
                        self.z = new_z

                # Проверяем расстояние для урона по игроку
                dy = abs(nearest_player.y - self.y)
                horizontal_distance = math.sqrt((self.x - nearest_player.x)**2 + (self.z - nearest_player.z)**2)
                
                if horizontal_distance < self.DAMAGE_DISTANCE * (self.scale / self.BASE_SCALE) and dy < 3:
                    nearest_player.take_damage(self.DAMAGE * self.damage_multiplier * 0.016)
                    return True
        return False

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'health': self.health,
            'is_alive': self.is_alive,
            'scale': self.scale,
            'speed': self.SPEED + self.speed_bonus
        }

class ZombieManager:
    def __init__(self, map_size):
        self.zombies = {}
        self.map_size = map_size
        self.next_zombie_id = 0
        self.walls = []
        self.plank_manager = None

    def set_plank_manager(self, plank_manager):
        self.plank_manager = plank_manager

    def set_walls(self, map_data):
        self.walls = [obj for obj in map_data if obj.get('texture') in ['brick', 'cobblestone']]

    def check_merge_zombies(self):
        merged_zombies = set()
        for id1, zombie1 in self.zombies.items():
            if id1 in merged_zombies:
                continue
            for id2, zombie2 in self.zombies.items():
                if id2 in merged_zombies or id1 == id2:
                    continue
                dx = zombie1.x - zombie2.x
                dz = zombie1.z - zombie2.z
                distance = (dx * dx + dz * dz) ** 0.5
                if distance < Zombie.MERGE_DISTANCE:
                    zombie1.merge_with(zombie2)
                    merged_zombies.add(id2)
        
        # Удаляем поглощенных зомби
        for zombie_id in merged_zombies:
            self.remove_zombie(zombie_id)

    def spawn_zombie(self, x, y, z):
        if not any(zombie.check_collision(x, z, self.walls) for zombie in self.zombies.values()):
            zombie_id = self.next_zombie_id
            zombie = Zombie(x, y, z)
            zombie.manager = self
            self.zombies[zombie_id] = zombie
            self.next_zombie_id += 1
            return zombie_id
        return None

    def update_zombies(self, players):
        # Сначала проверяем слияния
        self.check_merge_zombies()
        
        # Затем обновляем оставшихся зомби
        zombies_to_remove = []
        for zombie_id, zombie in self.zombies.items():
            if zombie.is_alive:
                zombie.move_towards_nearest_player(players, self.walls)
            else:
                zombies_to_remove.append(zombie_id)
        
        for zombie_id in zombies_to_remove:
            self.remove_zombie(zombie_id)

    def remove_zombie(self, zombie_id):
        if zombie_id in self.zombies:
            del self.zombies[zombie_id]

    def get_zombie(self, zombie_id):
        return self.zombies.get(zombie_id)

    def to_dict(self):
        return {str(zid): z.to_dict() for zid, z in self.zombies.items()}
