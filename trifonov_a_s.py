# -*- config: utf-8 -*-
from __future__ import annotations
from astrobox.core import Drone, Asteroid, MotherShip, GameObject
from robogame_engine.theme import theme
from robogame_engine.geometry import Vector, Point
from math import ceil, floor
from robogame_engine.states import StateMoving, StateTurning, StateStopped
from astrobox.space_field import Scene
from astrobox.guns import PlasmaProjectile


class TrifonovDrone(Drone):
    SPEED = theme.DRONE_SPEED
    TURN_SPEED = theme.DRONE_TURN_SPEED
    MAX_PAYLOAD = theme.MAX_DRONE_ELERIUM
    MAX_HEALTH = theme.DRONE_MAX_SHIELD

    count_drone = 0
    _step = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.head = None
        self._role = None
        TrifonovDrone.count_drone += 1

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, value):
        """
        Установить логику поведения дрона

        :param value: Класс поведения дрона
        """
        if value is None and self._role is not None:
            self._role.leave()
            self._role = None
            return
        elif value is None and self._role is None:
            return
        elif isinstance(self._role, value):
            return
        elif self._role is not None:
            self._role.leave()
        self._role = value(self)

    def on_born(self):
        self.head = Head.get_head(self)
        self.role = self.head.get_role(self)
        self._role.what_to_do()

    def on_stop_at_point(self, target):
        if self._role:
            self.role.on_stop_at_point(target)

    def on_stop_at_asteroid(self, asteroid):
        if self._role:
            self.role.on_stop_at_asteroid(asteroid)

    def on_stop_at_mothership(self, mothership):
        if self._role:
            self.role.on_stop_at_mothership(mothership)

    def on_load_complete(self):
        if self._role:
            self.role.on_load_complete()

    def on_unload_complete(self):
        if self._role:
            self.role.on_unload_complete()

    def on_heartbeat(self):
        TrifonovDrone._step += 1
        self.head.on_heartbeat(self)
        if self._role:
            self.role.on_heartbeat()

    def move_at(self, target, speed=None, reset=False):
        """
        :param reset: сброс последнего места назначения "_move_target".
        """
        point = target if isinstance(target, Point) else target.coord
        if is_point_eq(point, self.coord):
            return
        if reset:
            self._move_target = self.coord
        super(TrifonovDrone, self).move_at(target, speed)

    def turn_to(self, target, speed=None):
        point = target if isinstance(target, Point) else target.coord
        if is_point_eq(point, self.coord):
            return
        super(TrifonovDrone, self).turn_to(target, speed)

    @property
    def is_loading(self):
        """
            Дрон занят погрузкой элериума
        """
        return (self._transition is not None and self._transition.cargo_to == self._cargo and
                self._transition.cargo_from.payload)

    @property
    def is_unloading(self):
        """
            Дрон занят разгрузкой элериума
        """
        return self._transition is not None and self._transition.cargo_from == self._cargo

    def steps_to(self, point: Point):
        """
            Растояние до точки в шагах (step)
        """
        vector = Vector.from_points(self.coord, point, module=self.SPEED)
        if not vector.module:
            return 0
        distance = self.coord.distance_to(point)
        count_steps = ceil(distance / vector.module)
        count_steps += self.steps_to_turn(point)
        return count_steps

    def steps_to_turn(self, point: Point):
        """
            Шагов (step) для разварота на точку
        """
        vector = Vector.from_points(self.coord, point, module=self.SPEED)
        if not vector.module:
            return 0
        delta = abs(vector.direction - self.direction)
        delta = delta if delta <= 180 else 360 - delta
        return ceil(delta / self.TURN_SPEED)

    @property
    def move_target(self):
        """
        Точка назначения
        """
        return self._move_target

    def defeat_distance(self, target: GameObject):
        """
        Получить дистанцию поражения для объекта

        :param target: цель
        :return: дистанция порожения
        """
        return self.gun.projectile.max_distance + self.gun.projectile.radius + target.radius - 1

    def at_shot_distance(self, target):
        """
        Цель на растоянии выстрела
        :param target: цель
        """
        return self.defeat_distance(target) >= self.coord.distance_to(target.coord)

    @classmethod
    def step(cls):
        """
        Получить текущий ход

        :return: текущий ход
        """
        return cls._step // cls.count_drone * theme.HEARTBEAT_INTERVAL

    def shot(self, target):
        """
        Стрелять в цель

        :param target: цель
        """

        if target is None:
            return
        vector = Vector.from_points(self.coord, target.coord, module=self.SPEED)
        delta = abs(vector.direction - self.direction)
        if delta > 1:
            self.turn_to(target)
        else:
            if self.can_shot(target):
                self.gun.shot(target)

    def can_shot(self, target):
        """
        Могу стрелять по цели? (проверка огня по своим)

        :param target: цель
        """
        objects = [obj for obj in self.scene.objects if hasattr(obj, "damage_taken") and obj.is_alive]
        hit_obj = self.result_shot(self, self.coord, target.coord, objects)
        return hit_obj.team != self.team

    @staticmethod
    def result_shot(drone, place: Point, target: Point, objects):
        """
        Результат выстерла

        :param drone: дрон который стреляет
        :param place: места стрельбы
        :param target: цель
        :param objects: объекты, для которых производится расчет
        :return: объект, в который попали
        """
        # раудиус снаряда
        radius_projectile = drone.gun.projectile.radius
        vector = Vector.from_points(place, target, radius_projectile)
        x_min = min(place.x, target.x) - radius_projectile
        x_max = max(place.x, target.x) + radius_projectile
        y_min = min(place.y, target.y) - radius_projectile
        y_max = max(place.y, target.y) + radius_projectile

        hit_obj = []
        for obj in objects:
            if (obj.id == drone.id
                    or x_min > obj.coord.x + obj.radius or x_max < obj.coord.x - obj.radius
                    or y_min > obj.coord.y + obj.radius or y_max < obj.coord.y - obj.radius):
                continue
            # проэкция на линию огня
            if vector.x != 0 or vector.y != 0:
                delta_x = obj.coord.x - place.x
                delta_y = obj.coord.y - place.y
                t = vector.x * delta_x + vector.y * delta_y
                t = t / (vector.x ** 2 + vector.y ** 2)
                p_x = vector.x * t + place.x
                p_y = vector.y * t + place.y
                p_coord = Point(p_x, p_y)
            else:
                p_coord = place

            summa_radius = obj.radius + radius_projectile
            if abs(obj.coord.x - p_coord.x) > summa_radius and abs(obj.coord.y - p_coord.y) > summa_radius:
                continue
            distance = p_coord.distance_to(obj.coord)
            overlap_distance = int(summa_radius - distance)
            if overlap_distance > 1:
                hit_obj.append(obj)

        return min(hit_obj, key=lambda x: place.distance_to(x.coord) - x.radius) if hit_obj else None

    def can_hit(self, target):
        """
        Могу поразить?

        :param target: цель
        """
        if not self.at_shot_distance(target):
            return False
        objects = [obj for obj in self.scene.objects if hasattr(obj, "damage_taken") and obj.is_alive]
        hit_obj = self.result_shot(self, self.coord, target.coord, objects)
        return hit_obj.id == target.id


class SourceElerium:
    """
        Класс ИсточникЭлериума
        используется при нахождении маршрутов.
    """

    def __init__(self, asteroid, payload=None):
        if payload is None:
            self._payload = asteroid.payload
        else:
            self._payload = payload
        self._parent = asteroid

    @property
    def coord(self):
        return self._parent.coord

    @property
    def payload(self):
        return self._payload

    @payload.setter
    def payload(self, payload):
        if payload < 0:
            payload = 0
        self._payload = payload

    @property
    def parent(self):
        return self._parent

    def copy(self):
        return self.__class__(asteroid=self._parent, payload=self.payload)


class CounterStep:
    """
        Класс СчетчикХода.
        Имеет один метод для проверки нового хода
    """
    __step = 0

    @classmethod
    def _is_new_step(cls):
        """
        Наступил новый ход
        """
        result = cls.__step != TrifonovDrone.step()
        if result:
            cls.__step = TrifonovDrone.step()
        return result


class Head(CounterStep):
    """
        Класс Голова.
        Управляет дронами через назначение им ролей.
        Содержит интерфейс для общих методов команды. В частности содержит ссылку экземпляр класса Radar.
    """
    __head = None
    team = None
    scene = None
    all_elerium = 0
    drones = []
    teams = []
    radar = None
    #игровая статистика
    count_enemy_drones = 0
    health_matherships = 0
    payload = 0
    game_over_tics = 0
    count_step = 0

    class Team:
        """
            Класс команда, предназначен для оценки состояния протвиника
        """

        def __init__(self, scene, team):
            self.scene = scene
            self.team = team
            ships = [ship for ship in self.scene.motherships if ship.team == self.team and ship.is_alive]
            self.mothership = ships[0] if ships else None

        @property
        def is_alive(self):
            """
                Команда жива
            """
            return self.drones or self.mothership

        @property
        def drones(self):
            """
                Список дронов команды
            """
            return [drone for drone in self.scene.drones if drone.team == self.team and drone.is_alive]

    @classmethod
    def get_head(cls, drone: TrifonovDrone):
        cls.drones.append(drone)
        if cls.__head is None:
            cls.__head = Head(drone)
        return cls.__head

    def __init__(self, drone: TrifonovDrone):
        """
        Не использовать, для получения головы использовать функцию get_head
        :param drone: дрон
        """
        if drone not in Head.drones:
            raise NameError("для получения головы использовать функцию Head.get_head")
        Head.all_elerium = sum(asteroid.payload for asteroid in drone.asteroids)
        Head.scene = drone.scene
        Head.team = drone.team
        Head.radar = Radar(drone.scene, drone.team)
        Head.count_enemy_drones, Head.health_matherships = Head._refresh_teams()

        Head.payload = Head.all_elerium
        # нужно тиков что бы дрону пролететь экран по диагонали
        screen_diagonal = (theme.FIELD_WIDTH ** 2 + theme.FIELD_HEIGHT ** 2) ** .5
        Head._game_over_tics = int(screen_diagonal / theme.DRONE_SPEED / theme.HEARTBEAT_INTERVAL * 0.8)

    @staticmethod
    def _refresh_teams():
        """
            Обновление данных о коммандах соперника в Head.team
        :return: общее число дронов соперника, общее здоровье материнских короблей противника
        """
        count_enemy_drones = 0
        health_matherships = 0
        Head.teams.clear()
        for team in Head.scene.teams:
            if team == Head.team:
                continue
            new_team = Head.Team(Head.scene, team)
            if new_team.mothership:
                health_matherships += new_team.mothership.health
            if new_team.is_alive:
                count_enemy_drones += len(new_team.drones)
                Head.teams.append(new_team)
        return count_enemy_drones, health_matherships

    @staticmethod
    def get_role(drone: TrifonovDrone):
        """
            Получит роль

            :return: класс роль (Role)
        """
        if drone.role is None:
            if Head.teams:
                return Defender
            else:
                return Collector

    @staticmethod
    def on_heartbeat(drone: TrifonovDrone):
        """
            Для вызова дроном при обработке своего события on_heartbeat.
            В этом методе реализуется стратегия по распределеию/смене ролей дронов.
        """
        if drone in Head.drones and not drone.is_alive:
            drone.role = None
            Head.drones.remove(drone)
            return

        if not drone.is_alive:
            return

        Head.radar.reflect()
        if Head._is_new_step():
            count_enemy_drones, health_matherships = Head._refresh_teams()
            if count_enemy_drones == Head.count_enemy_drones and (Head.health_matherships - health_matherships) < 500:
                Head.count_step += 5
            else:
                Head.count_step = 0
                Head.count_enemy_drones = count_enemy_drones
                Head.health_matherships = health_matherships
            new_payload = Router.get_list_source_elerium(Head.scene)
            if new_payload != Head.payload or Head.count_step == 0:
                Head.game_over_tics = Head._game_over_tics
            else:
                Head.game_over_tics -= 1
                if Head.game_over_tics < 0:
                    Head.count_step = 501

        if Head.count_step > 500:
            Head.count_step = 0
            if Combat.limit_distance == 0:
                Combat.limit_distance = 500
                for _drone in Head.drones:
                    _drone.role = Combat
                return
            elif Combat.limit_distance < 900:
                Combat.limit_distance += 100
            else:
                for _drone in Head.drones:
                    _drone.role = Collector
                return

        if not Head.teams:
            if not isinstance(drone.role, Collector):
                drone.role = Collector
                Head.count_step = 0
        elif sum(obj.payload for obj in Router.get_list_source_elerium(Head.scene)) == 0 or len(Head.drones) <= 2:
            if drone.payload == 0:
                drone.role = Defender


class Router:
    """
        Класс маршрутизатор
    """
    is_working = False
    source_elerium = []
    half_all_elerium = None

    def __init__(self, drone: TrifonovDrone):
        self._drone = drone
        self._destination = None
        self._payload = None
        self._scheduled_free_space = None

        if not Router.is_working:
            Router.is_working = True
            Router.half_all_elerium = Head.all_elerium // 2

    def destination(self, assume=False) -> GameObject:
        """
        :param assume: предположить следующую точку
        :return: координаты места назначения
        """
        self._refresh()
        if assume:
            free_space = self._scheduled_free_space
            if not free_space and self._destination.payload < self._drone.free_space:
                free_space = self._drone.free_space - self._destination.payload
        else:
            free_space = self._drone.free_space

        if not free_space:
            destination = self._drone.my_mothership
            payload = 0
            scheduled_free_space = self._drone.MAX_PAYLOAD
        else:
            destination, payload, scheduled_free_space = self._get_destination(free_space)

        if not assume:
            self._payload = payload
            self._scheduled_free_space = scheduled_free_space
            self._destination = destination

        return destination

    @property
    def payload(self):
        return self._payload

    def _refresh(self):
        """
        Актулизировать список источников_элериума Router.source_elerium = [SourceElerium, ...]
        """
        Router.source_elerium = self.get_list_source_elerium(scene=self._drone.scene)
        if Router.source_elerium:
            for drone in Collector.drones:
                drone.role.router.update_source_elerium()

    @staticmethod
    def get_list_source_elerium(scene):
        """
        Получить список источников элериума
        :scene: сцена игры
        :return: список источников элериума [SourceElerium, ...]
        """
        list_source_elerium = []
        for obj in scene.objects:
            if isinstance(obj, Asteroid) or isinstance(obj, (MotherShip, Drone)) and not obj.is_alive:
                if obj.payload != 0:
                    list_source_elerium.append(SourceElerium(obj))
        return list_source_elerium

    def _get_source_elerium(self, free_space) -> SourceElerium:
        """
        Получить источник элериума для сбора элериума

        :param free_space: свободное место в трюме дрона
        :return: источник элериума
        """
        # выбор стратегии
        if sum(source_elerium.payload for source_elerium in Router.source_elerium) <= Router.half_all_elerium:
            price = self.distance
        else:
            price = self.route_price

        prices_drone_source_elerium = [
            (self._drone, source_elerium, price(drone=self._drone, source_elerium=source_elerium,
                                                free_space=free_space) * self.level_danger(source_elerium))
            for source_elerium in Router.source_elerium
        ]
        prices_drone_source_elerium.sort(key=lambda x: x[2])
        preferred_source_elerium = prices_drone_source_elerium[0][1]

        drones = self._drone.role.get_free_drones()
        while prices_drone_source_elerium:
            _price = prices_drone_source_elerium.pop(0)
            source_elerium = _price[1]
            prices_source_elerium_drones = [
                (drone, source_elerium, price(drone=drone, source_elerium=source_elerium, free_space=drone.free_space))
                for drone in drones
            ]
            prices_source_elerium_drones.append(_price)
            min_price = min(prices_source_elerium_drones, key=lambda x: x[2])
            if min_price == _price:
                preferred_source_elerium = source_elerium
                break
            else:
                drones.remove(min_price[0])

        return preferred_source_elerium

    def _get_destination(self, free_space):
        """
        Получить место назначение.

        :param free_space: свободное место в трюме дрона
        :return: место назначение (GameObject); кол-во элериума подлежащих к загрузке;
         планируемое свободное место после погрузки
        """
        if Router.source_elerium:
            source_elerium = self._get_source_elerium(free_space)

            payload = source_elerium.payload if source_elerium.payload <= free_space else free_space
            scheduled_free_space = free_space - payload
            destination = source_elerium.parent

        elif sum(source_elerium for source_elerium in Router.source_elerium):
            Router.source_elerium = self.get_list_source_elerium(self._drone.scene)
            destination, payload, scheduled_free_space = self._get_destination(free_space)

        else:
            destination = self._drone.my_mothership
            payload = 0
            scheduled_free_space = self._drone.MAX_PAYLOAD
        return destination, payload, scheduled_free_space

    @property
    def is_destination_valid(self):
        """
        Текущее место назначение действительно
        """
        if self._drone.mothership == self._destination:
            return True
        elif hasattr(self._destination, "payload"):
            return self._destination.payload > 0
        else:
            return False

    @staticmethod
    def route_price(drone: TrifonovDrone, source_elerium: SourceElerium, free_space, **kwargs):
        """
        Цена маршрута на единицу элериума

        :param drone: дрон
        :param source_elerium: источник элериума
        :param free_space: свободное место в дроне
        :return: цена маршрута да источника элериума
        """
        payload = source_elerium.payload if source_elerium.payload < free_space else free_space
        return drone.steps_to(source_elerium.coord) / payload

    @staticmethod
    def distance(drone, source_elerium, **kwargs):
        """
        Растояние до астеройда

        :param drone: дрон
        :param source_elerium: источник элериума
        :return: количество шагов до источника элериума
        """
        return drone.steps_to(source_elerium.coord)

    def update_source_elerium(self):
        """
            Обновляет payload источник элериума c которым взаимодействует в Router.source_elerium
        """
        if isinstance(self._destination, SourceElerium):
            payload = self._drone.MAX_PAYLOAD - self._scheduled_free_space - self._drone.payload
            for source_elerium in Router.source_elerium:
                if source_elerium.coord == self._destination.coord:
                    source_elerium.payload -= payload
                    if not source_elerium.payload:
                        Router.source_elerium.remove(source_elerium)
                    break

    def level_danger(self, source_elerium: SourceElerium):
        """
            Уровеннь опасности
        :param source_elerium:источник элериума (SourceElerium)
        :return: уровень опасности
        """
        drones = [drone for drone in self._drone.scene.drones if drone.is_alive and drone.team != self._drone.team]
        sources_elerium = self.get_list_source_elerium(self._drone.scene)
        level = 1
        for drone in drones:
            if self._drone.defeat_distance(drone) < drone.coord.distance_to(source_elerium.coord):
                continue
            else:
                level += 1
            if (isinstance(drone.state, StateStopped) or
                    (isinstance(drone.state, StateTurning) and not drone.state.move_at_target)):
                for source in sources_elerium:
                    if is_coord_eq(drone.coord, source.coord):
                        break
                else:
                    level += 5
        return level


class Role(CounterStep):
    """
        Базовый клас Роль.
        Обеспечивает логику дрона
    """

    def __init__(self, drone: TrifonovDrone):
        self._drone = drone

    def leave(self):
        """
            Вызыватся при оставлении дроном роли
        """
        pass

    def what_to_do(self):
        pass

    def on_stop_at_point(self, target):
        pass

    def on_stop_at_asteroid(self, asteroid):
        pass

    def on_stop_at_mothership(self, mothership):
        pass

    def on_load_complete(self):
        pass

    def on_unload_complete(self):
        pass

    def on_heartbeat(self):
        pass


class Collector(Role):
    """
        Роль - собирателя ресурсов
    """
    router = None
    drones = []
    targets_for_shot = []

    def __init__(self, drone):
        super(Collector, self).__init__(drone)
        self.rookie = True
        Collector.drones.append(self._drone)
        self.router = Router(self._drone)

    def leave(self):
        Collector.drones.remove(self._drone)

    def get_free_drones(self):
        """
        Получить список не занятых дронов (за исключением себя)

        :return: [TrifonovDrone, ...]
        """
        return [drone for drone in Collector.drones if not self.is_busy and not drone.is_full]

    def what_to_do(self):
        if self.is_busy and not self.rookie:
            if not self.is_moving_at_valid_destination:
                target_for_shot = self.target_fot_shot()
                if target_for_shot:
                    self._drone.shot(target_for_shot)
                else:
                    target = self.router.destination(assume=True)
                    self._drone.turn_to(target)
        else:
            target = self.router.destination()
            if (target == self._drone.move_target
                    and is_coord_eq(target.coord, self._drone.coord) and target != self._drone.mothership):
                # уже на месте, нужно загрузить сколько влезет
                self._drone.load_from(target)
            else:
                self._drone.move_at(target)
        self.rookie = False

    def on_stop_at_point(self, target):
        sources = self.router.get_list_source_elerium(self._drone.scene)
        nearest_source = min(sources, key=lambda source: self._drone.distance_to(source.parent)) if sources else None
        if nearest_source:
            self._drone.load_from(nearest_source.parent)

    def on_stop_at_asteroid(self, asteroid):
        if is_coord_eq(asteroid.coord, self._drone.move_target) and asteroid.payload > 0:
            self._drone.load_from(asteroid)
        else:
            self.on_stop_at_point(self._drone.coord)

    def on_stop_at_mothership(self, mothership):
        if mothership.team == self._drone.team:
            self._drone.unload_to(mothership)
        else:
            self.on_stop_at_point(self._drone.coord)

    def on_load_complete(self):
        self.what_to_do()

    def on_unload_complete(self):
        self.what_to_do()

    def on_heartbeat(self):
        if self._is_new_step():
            Collector.targets_for_shot.clear()

        if (self._drone.head.radar.health(self._drone) <= self._drone.MAX_HEALTH * 0.6 and
                self._drone.coord.distance_to(self._drone.mothership.coord) > theme.MOTHERSHIP_HEALING_DISTANCE):
            self._drone.move_at(self._drone.my_mothership, reset=True)
        else:
            self.what_to_do()

    @property
    def is_moving_at_valid_destination(self):
        """
            Дрон двигается к действительной цели
        """
        is_moving = isinstance(self._drone.state, StateMoving) or (isinstance(self._drone.state, StateTurning)
                                                                   and self._drone.state.move_at_target)
        return is_moving and self.router.is_destination_valid

    @property
    def is_busy(self):
        """
            Дрон занят.
            Дрон либо грузит, либо разгружает, либо двигается к действительной цели.
            Однако, если в трюмах всех дронов достаточно места для остатков элериума
            дрон будет обозначатся свободным.
        """
        collect_all_drones = sum(source_elerium.payload for source_elerium in self.router.source_elerium) <= sum(
            drone.free_space for drone in self.drones) and not self._drone.is_full
        return self._drone.is_loading or self.is_moving_at_valid_destination or (
                self._drone.is_unloading and not collect_all_drones)

    def target_fot_shot(self):
        targets = [obj for obj in Collector.targets_for_shot if self._drone.can_hit(obj)]

        if not targets:
            targets = [drone for drone in self._drone.scene.drones if drone.team != self._drone.team and drone.is_alive
                       and Head.radar.health(drone) > 0 and self._drone.can_hit(drone) and
                       (drone.coord.distance_to(drone.mothership.coord) > theme.MOTHERSHIP_HEALING_DISTANCE or
                        not drone.mothership.is_alive)]

        target = min(targets, key=lambda x: self._drone.steps_to_turn(x.coord)) if targets else None
        if target and target not in Collector.targets_for_shot:
            Collector.targets_for_shot.append(target)
        return target


class Defender(Role):
    """
        Роль - защитник материнского корабля
    """
    drones = []
    positions = []
    targets = []

    class Position:
        def __init__(self, coord):
            self.coord = coord
            self.owner = None

        def occupy(self, owner: Defender):
            """
            Зянять позицию.

            :param owner: Защитник (не дрон, его роль)
            """
            self.owner = owner
            self.owner.position = self

        def leave(self):
            """
            Освободить позицию.
            """
            self.owner.position = None
            self.owner = None

        @property
        def is_free(self):
            """
            Позиция свободна
            """
            return self.owner is None

    def __init__(self, drone):
        super(Defender, self).__init__(drone)
        self.position = None
        self.timer_change_position = 0
        Defender.drones.append(self._drone)
        if not Defender.positions:
            self._init_place()

    def _init_place(self):
        """
        Создание позиций для обороны
        """
        center = self._drone.mothership.coord
        radius = theme.MOTHERSHIP_HEALING_DISTANCE - 1
        if center.x < self._drone.scene.field[0] // 2:
            min_x = self._drone.radius
            max_x = center.x + radius
        else:
            min_x = center.x - radius
            max_x = self._drone.scene.field[0] - self._drone.radius

        if center.y < self._drone.scene.field[1] // 2:
            sign_y = -1
            min_y = self._drone.radius
            max_y = center.y + radius
        else:
            sign_y = 1
            min_y = center.y - radius
            max_y = self._drone.scene.field[1] - self._drone.radius

        x = center.x
        y = center.y + sign_y * radius
        vector = Vector.from_points(center, Point(x, y))
        for angle in range(0, 361):
            vector.rotate(angle)
            x = vector.x + center.x
            if x < min_x or x > max_x:
                continue
            y = vector.y + center.y
            if y < min_y or y > max_y:
                continue
            new_position = Point(x, y)
            if not Defender.positions:
                Defender.positions.append(Defender.Position(new_position))
            for position in Defender.positions:
                if new_position.distance_to(position.coord) < self._drone.radius + self._drone.gun.projectile.radius:
                    break
            else:
                Defender.positions.append(Defender.Position(new_position))

    def leave(self):
        self.leave_position()
        Defender.drones.remove(self._drone)

    def get_position(self, can_hit=False):
        """
        Получить позицию

        :param can_hit: С данной позиции есть кого пострелять
        :return: позицию или None
        """
        positions = tuple((position, self._drone.steps_to(position.coord)) for position in Defender.positions
                          if position.is_free)
        if can_hit:
            new_positions = []
            for position in positions:
                coord = position[0].coord
                for drone in self._drone.scene.drones:
                    if (drone.team != self._drone.team and drone.is_alive and Head.radar.health(drone) > 0 and
                            drone.coord.distance_to(coord) <= self._drone.defeat_distance(drone)):
                        new_positions.append(position)
                        break
                if not new_positions:
                    for ship in self._drone.scene.motherships:
                        if (ship.team != self._drone.team and ship.is_alive
                                and ship.coord.distance_to(coord) <= self._drone.defeat_distance(ship)):
                            new_positions.append(position)
                            break
            positions = new_positions

        return min(positions, key=lambda x: x[1])[0] if positions else None

    def what_to_do(self):
        if self.position is None:
            position = self.get_position()
            if position is None:
                self._drone.move_at(self._drone.mothership)
            else:
                position.occupy(self)
                self._drone.move_at(self.position.coord)
            return
        elif is_coord_eq(self._drone.coord, self.position.coord):
            target = self.get_target()
            if target is None:
                self.timer_change_position += 1
                if self.timer_change_position > 4:
                    self.change_position()
                    self.timer_change_position = 0
            else:
                self._drone.shot(target)

    def get_target(self):
        """
        Получить цель

        :return: цель (Drone, Mothership)
        """
        targets = [obj for obj in Defender.targets if self._drone.can_hit(obj)]

        if not targets:
            targets = [drone for drone in self._drone.scene.drones if drone.team != self._drone.team and drone.is_alive
                       and Head.radar.health(drone) > 0 and self._drone.can_hit(drone) and
                       (drone.coord.distance_to(drone.mothership.coord) > theme.MOTHERSHIP_HEALING_DISTANCE or
                        not drone.mothership.is_alive)]

        if not targets:
            targets = [ship for ship in self._drone.scene.motherships if ship.team != self._drone.team
                       and ship.is_alive and self._drone.can_hit(ship)]

        target = min(targets, key=lambda x: self._drone.mothership.coord.distance_to(x.coord)) if targets else None
        if target and target not in Defender.targets:
            Defender.targets.append(target)
        return target

    def on_heartbeat(self):
        if self._is_new_step():
            Defender.targets.clear()

        if self._drone.head.radar.health(self._drone) <= self._drone.MAX_HEALTH * 0.5:
            self.leave_position()
            self._drone.move_at(self._drone.mothership.coord, reset=True)
        else:
            self.what_to_do()

    def leave_position(self):
        """
        Освободить занимаемую позицию
        """
        if self.position is not None:
            self.position.leave()

    def change_position(self):
        """
        Сменить позицию, на ту что позволяет вести огонь
        """
        position = self.get_position(can_hit=True)
        if position:
            self.leave_position()
            position.occupy(self)
            self._drone.move_at(self.position.coord)


class Radar:
    """
     Класс Радар, на данный момент система предупреждения о попадании
    """

    def __init__(self, scene: Scene, team):
        self._scene = scene
        self.team = team
        self.hits = []

    def reflect(self):
        """
        Фиксация выстрелов и их предполагаемых результатов
        """
        self.hits = []
        for obj in self._scene.objects:
            if not isinstance(obj, PlasmaProjectile) or not obj.is_alive:
                continue
            projectile = ConditionalProjectile(obj)
            projectile.result()
            if projectile.hit_obj:
                self.hits.append((projectile.hit_obj, projectile.step, projectile.damage))

    def health(self, drone: Drone):
        """
        Прогнозируемое здоровье дрона при попадании выпущенных в него снарядов

        :param drone: дрон
        :return: здоровье
        """
        health = drone.health
        hits = [hit for hit in self.hits if hit[0] == drone]
        step = 0
        while hits:
            step += 1
            for hit in hits.copy():
                if step == hit[1]:
                    health -= hit[2]
                    hits.remove(hit)
            if health <= 0:
                break
            health = min(theme.DRONE_MAX_SHIELD, health + self.health_gain_per_turn(drone))
        return health

    @staticmethod
    def health_gain_per_turn(drone: Drone):
        """
        Прирост здоровья дрона за ход

        :param drone: дрон
        :return:здоровье
        """
        health = theme.MOTHERSHIP_SHIELD_RENEWAL_RATE
        if drone.coord.distance_to(drone.mothership) < theme.MOTHERSHIP_HEALING_DISTANCE:
            health += theme.MOTHERSHIP_HEALING_RATE
        return health


class ConditionalProjectile:
    """
    Класс условный сняряд, используется для Радара
    """

    def __init__(self, obj, **kwargs):
        projectile = obj
        self.coord = projectile.coord.copy()
        self.direction = projectile.direction
        self.ttl = projectile.ttl
        self.radius = projectile.radius
        self.owner = projectile.owner
        self.objects = projectile.scene.objects
        self.step = 0
        self.hit_obj = None

        if isinstance(projectile.state, StateMoving):
            self.is_moving = True
            self.target_point = projectile.state.target_point
            self.vector = Vector.from_points(self.coord, self.target_point, module=theme.PROJECTILE_SPEED)
        else:
            self.is_moving = False
            self.target_point = None
            self.vector = None

    @property
    def damage(self):
        """
        Нанасоимый урон при попадании

        :return: урон
        """
        return theme.PROJECTILE_DAMAGE

    def result(self):
        """
        Результат выстерела

        :return: объект куда попали, сколько ходов до попадания
        """
        while self.is_alive:
            self.game_step()
        return self.hit_obj, self.step

    def _step(self):
        """
        Полет снаряда за ход игры
        """
        if self.is_moving:
            distance_to_target = self.coord.distance_to(self.target_point)
            if distance_to_target < self.vector.module:
                self.coord += Vector.from_direction(self.vector.direction, distance_to_target)
                self.is_moving = False
            else:
                self.coord += self.vector

    def game_step(self):
        """
        Ход игры для снаряда
        """
        self.step += 1
        self.ttl = max(self.ttl - 1, 0)
        self._step()
        # проверка на попадание в объект
        for obj in self.objects:

            if not hasattr(obj, "damage_taken") or obj.team is None or not obj.is_alive:
                continue
            if theme.TEAM_DRONES_FRIENDLY_FIRE:
                # Не наносим урон себе
                if obj.id == self.owner.id:
                    continue
            else:
                # Пролетаем свои объекты
                if obj.team == self.owner.team:
                    continue

            summa_radius = obj.radius + self.radius
            if abs(obj.coord.x - self.coord.x) > summa_radius and abs(obj.coord.y - self.coord.y) > summa_radius:
                continue
            distance = self.coord.distance_to(obj.coord)
            overlap_distance = int(summa_radius - distance)
            if overlap_distance > 1:
                # попадание
                self.ttl = 0
                self.is_moving = False
                self.hit_obj = obj
                break

    @property
    def is_alive(self):
        return self.ttl > 0


class Combat(Role):
    """
    Роль - боец
    """
    drones = []
    places_attacks = {}
    limit_distance = 0

    def __init__(self, drone):
        super().__init__(drone)
        Combat.drones.append(self._drone)

    def leave(self):
        Combat.drones.remove(self._drone)

    def what_to_do(self):
        target = self.get_target()
        if target is None:
            self._drone.move_at(self._drone.mothership)
            return

        place = self.get_place(target)
        if place is None:
            self._drone.move_at(self._drone.mothership)
            return

        if not is_point_eq(self._drone.coord, place):
            self._drone.move_at(place)
        elif isinstance(self._drone.state, (StateStopped, StateTurning)):
            self._drone.shot(target)

    def get_target(self):
        """
        Получить цель

        :return: цель (Drone, Mothership)
        """
        targets = [drone for drone in Head.scene.drones if drone.team != self._drone.team and drone.is_alive and
                   Head.radar.health(drone) > 0]

        if not targets:
            targets = [ship for ship in Head.scene.motherships if ship.team != self._drone.team and ship.is_alive]
        if not targets:
            return None

        if self._drone.mothership.health >= theme.MOTHERSHIP_MAX_SHIELD * 0.9:
            koef = 3
        else:
            koef = 0
        dict_target = {}
        for drone in Combat.drones:
            for target in targets:
                dict_target[target] = (dict_target.setdefault(target, 0) + drone.steps_to(target.coord) * koef)
        for target in targets:
            dict_target[target] += self._drone.my_mothership.coord.distance_to(target.coord)

        target = min(dict_target, key=lambda x: dict_target[x])

        if isinstance(target, Drone) and target.mothership.is_alive and \
                (target.coord.distance_to(target.mothership.coord) <= theme.MOTHERSHIP_HEALING_DISTANCE):
            target = target.mothership

        return target

    def get_place(self, target):
        """
        Получить место для атаки
        :param target: цель

        :return: место (Point или None)
        """
        defeat_distance = self._drone.defeat_distance(target)
        dict_places = Combat.places_attacks.setdefault(target, {})
        if not dict_places:
            for drone in Combat.drones:
                distance_to_target = drone.coord.distance_to(target.coord)
                if distance_to_target <= defeat_distance:
                    place = drone.coord
                    if self.is_place_valid(drone, place, target):
                        dict_places[drone] = place
        place = dict_places.get(self._drone)
        if place:
            return place

        step_find = self._drone.radius * 2
        min_x = max(ceil(-defeat_distance + target.x), self._drone.radius)
        max_x = min(floor(defeat_distance + target.x), theme.FIELD_WIDTH - self._drone.radius)
        min_y = max(ceil(-defeat_distance + target.y), self._drone.radius)
        max_y = min(floor(defeat_distance + target.y), theme.FIELD_HEIGHT - self._drone.radius)

        min_distance_to_place = None
        optimal_place = None
        for x in range(min_x, max_x, step_find):
            for y in range(min_y, max_y, step_find):
                place = Point(x, y)
                if self.point_in_circle(point=place, center=target.coord, radius=defeat_distance) and \
                        self.is_place_valid(self._drone, place, target):
                    distance_to_place = self._drone.steps_to(place) + self._drone.steps_to_turn(target.coord)
                    if min_distance_to_place is None or distance_to_place < min_distance_to_place:
                        min_distance_to_place = distance_to_place
                        optimal_place = place
        if optimal_place:
            dict_places[self._drone] = optimal_place
        return optimal_place

    @staticmethod
    def point_c_at_line(a: Point, b: Point, len_ac):
        """
        Найти точку на прямой

        :param a: начальная точка на прямой
        :param b: конечная точка на прямой
        :param len_ac: длина орезка AC
        :return:
        """
        len_ab = a.distance_to(b)
        x = a.x + (b.x - a.x) * len_ac / len_ab
        y = a.y + (b.y - a.y) * len_ac / len_ab
        return Point(x, y)

    @staticmethod
    def point_in_circle(point: Point, center: Point, radius):
        """
        Точка находится в окружности

        :param point: точка
        :param center: центр окружности
        :param radius: радиус окружности
        :return:
        """
        return radius ** 2 - ((center.x - point.x) ** 2 + (center.y - point.y) ** 2) >= 0

    def is_place_valid(self, drone, place: Point, target):
        """
        Место подходит для атаки?

        :param drone: атакующий дрон
        :param place: место атаки
        :param target: цель
        """

        class MyDrone:
            """
            Вспомагательный класс, для эмуляции дронов в своих позициях
            """

            def __init__(self, drone: TrifonovDrone, coord, target):
                self.drone = drone
                self.coord = coord.copy()
                self.target = target
                self.id = drone.id
                self.radius = drone.radius

        if 0 < Combat.limit_distance < place.distance_to(drone.mothership):
            return False

        # не должен быть рядом чужих живых материнских короблей
        for ship in Head.scene.motherships:
            if ship.team == Head.team or not ship.is_alive:
                continue
            if drone.radius + ship.radius > place.distance_to(ship.coord):
                return False

        # создаем объекты для просчета стрельбы
        objects = [MyDrone(drone, place, target)]
        for key_target in Combat.places_attacks.keys():
            for drone, coord in Combat.places_attacks[key_target].items():
                objects.append(MyDrone(drone, coord, key_target))

        for obj in self._drone.scene.objects:
            if isinstance(obj, (Drone, MotherShip)) and obj.is_alive and obj not in Combat.drones:
                objects.append(obj)

        # перестрелка
        for obj in objects:
            if isinstance(obj, MyDrone):
                if target != self._drone.result_shot(drone=obj.drone, place=obj.coord, target=obj.target.coord,
                                                     objects=objects):
                    return False
        return True

    def on_heartbeat(self):
        if self._is_new_step():
            Combat.places_attacks.clear()

        if (self._drone.head.radar.health(self._drone) <= self._drone.MAX_HEALTH * 0.6 and
                self._drone.coord.distance_to(self._drone.mothership.coord) > theme.MOTHERSHIP_HEALING_DISTANCE):
            self._drone.move_at(self._drone.my_mothership, reset=True)
        else:
            self.what_to_do()


def is_point_eq(point_1: Point, point_2: Point):
    """
    Проверяет равенство(идентичность) точек

    :param point_1: точка 1
    :param point_2: точка 2
    """
    if point_1 is None or point_2 is None:
        return False
    return point_1.x == point_2.x and point_1.y == point_2.y


def is_coord_eq(coord_1: Point, coord_2: Point):
    """
    Проверяет равенсто координат с учетом погрешности CARGO_TRANSITION_DISTANCE
    """
    delta = abs(coord_1.x + coord_1.y - coord_2.x - coord_2.y)
    return delta <= theme.CARGO_TRANSITION_DISTANCE


drone_class = TrifonovDrone
