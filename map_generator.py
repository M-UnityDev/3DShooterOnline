import random
import math

def generate_map(size):
    """Генерирует большую карту с разными текстурами."""
    map_objects = []
    
    # Увеличиваем размер карты еще больше
    actual_size = size * 4  # Умножаем на 4 вместо 2
    
    # Основная платформа (пол) с травой
    floor = {
        'x': 0,
        'y': -1,
        'z': 0,
        'scale_x': actual_size,
        'scale_y': 1,
        'scale_z': actual_size,
        'rotation_y': 0,
        'texture': 'grass'
    }
    map_objects.append(floor)
    
    # Генерация стен
    num_walls = random.randint(30, 50)  # Увеличиваем количество стен
    
    for _ in range(num_walls):
        x = random.uniform(-actual_size/2 + 8, actual_size/2 - 8)
        z = random.uniform(-actual_size/2 + 8, actual_size/2 - 8)
        
        width = random.uniform(4, 12)  # Увеличиваем размеры стен
        height = random.uniform(6, 12)
        depth = random.uniform(2, 6)
        
        rotation = random.choice([0, 45, 90, 135, 180, 225, 270, 315])
        
        wall = {
            'x': x,
            'y': height/2 - 1,
            'z': z,
            'scale_x': width,
            'scale_y': height,
            'scale_z': depth,
            'rotation_y': rotation,
            'texture': 'brick'
        }
        
        spawn_distance = math.sqrt(x*x + z*z)
        if spawn_distance > 12:  # Увеличиваем безопасную зону
            map_objects.append(wall)
    
    # Добавляем внешние стены (барьер)
    barrier_height = 12  # Увеличиваем высоту барьера
    barrier_thickness = 3  # Увеличиваем толщину барьера
    
    # Четыре стены по периметру с текстурой булыжника
    barriers = [
        # Северная стена
        {
            'x': 0,
            'y': barrier_height/2 - 1,
            'z': actual_size/2 + barrier_thickness/2,
            'scale_x': actual_size + barrier_thickness*2,
            'scale_y': barrier_height,
            'scale_z': barrier_thickness,
            'rotation_y': 0,
            'texture': 'cobblestone'
        },
        # Южная стена
        {
            'x': 0,
            'y': barrier_height/2 - 1,
            'z': -actual_size/2 - barrier_thickness/2,
            'scale_x': actual_size + barrier_thickness*2,
            'scale_y': barrier_height,
            'scale_z': barrier_thickness,
            'rotation_y': 0,
            'texture': 'cobblestone'
        },
        # Восточная стена
        {
            'x': actual_size/2 + barrier_thickness/2,
            'y': barrier_height/2 - 1,
            'z': 0,
            'scale_x': barrier_thickness,
            'scale_y': barrier_height,
            'scale_z': actual_size,
            'rotation_y': 0,
            'texture': 'cobblestone'
        },
        # Западная стена
        {
            'x': -actual_size/2 - barrier_thickness/2,
            'y': barrier_height/2 - 1,
            'z': 0,
            'scale_x': barrier_thickness,
            'scale_y': barrier_height,
            'scale_z': actual_size,
            'rotation_y': 0,
            'texture': 'cobblestone'
        }
    ]
    
    map_objects.extend(barriers)
    return map_objects

