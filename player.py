class Player:
    def __init__(self, x, y, z, nickname="Player"):
        self.x = x
        self.y = y
        self.z = z
        self.health = 100
        self.max_health = 100
        self.is_alive = True
        self.nickname = nickname
        self.zombie_kills = 0
        self.is_ghost = False
        self.shoot_cooldown = 1.0
        self.planks_count = 0
        self.placing_plank = False
        self.placing_wall = False
        self.rotation = 0
        self.animation_state = 'idle'
        self.delta_time = 0.016  # Пример значения, можно получить из игрового цикла
        self.is_grounded = True
        self.last_y = y

    def take_damage(self, damage):
        if not self.is_ghost and self.is_alive:  # Проверяем, что игрок жив и не призрак
            self.health -= damage
            if self.health <= 0:
                self.health = 0
                self.is_alive = False
                self.is_ghost = True

    def set_position(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def add_kill(self):
        self.zombie_kills += 1

    def update_animation_state(self, state):
        self.animation_state = state

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'health': self.health,
            'is_alive': self.is_alive,
            'is_ghost': self.is_ghost,
            'nickname': self.nickname,
            'zombie_kills': self.zombie_kills,
            'shoot_cooldown': self.shoot_cooldown,
            'planks_count': self.planks_count,
            'rotation': self.rotation
        }
