import time
import json
import paho.mqtt.client as mqtt

MQTT_SERVER = "192.168.140.132"
MQTT_PORT = 1883
TRANSFER_TOPIC = "command/transfer"

# 명령세트를 체계적으로 관리하기 위한 클래스 정의
class CommandSet:
    def __init__(self, robot_id, path, initial_dir="north"):
        """
        robot_id: 제어할 로봇의 ID (문자열)
        path: 로봇의 경로 (예: [(0, 0), (0, 1), (1, 1)])
        initial_dir: 로봇의 초기 방향 (예: "north")
        """
        self.robot_id = robot_id
        self.path = path
        self.initial_dir = initial_dir
        self.commands = self.path_to_commands()
        self.command_count = len(self.commands)

    def path_to_commands(self):
        if not self.path or len(self.path) < 2:
            return []

        commands = []
        current_dir = self.initial_dir
        i = 0
        N = len(self.path)

        while i < N - 1:
            pos1 = self.path[i]
            pos2 = self.path[i + 1]
            # 방향 계산
            next_dir = self.direction_between(pos1, pos2)

            # 방향 전환 명령
            if current_dir != next_dir:
                commands.append(self.turn_command(current_dir, next_dir))
                current_dir = next_dir

            # 같은 방향으로 연속된 구간 합산
            total_steps = 0
            # 다음 경로가 같은 방향인 동안 반복
            while i < N - 1 and self.direction_between(self.path[i], self.path[i+1]) == current_dir:
                # 한 칸 거리는 1 그리드
                total_steps += self.distance_between(self.path[i], self.path[i+1])
                i += 1

            # 예) total_steps == 3 이면 D3, 
            # 실제 cm 단위로 보내야 하면 f"D{total_steps * 10}" 처럼 곱해 주세요
            commands.append(f"D{total_steps}")

        return commands

    def direction_between(self, pos1, pos2):
        """
        두 좌표 간의 방향을 계산합니다.
        """
        r1, c1 = pos1
        r2, c2 = pos2
        if r1 == r2 and c1 + 1 == c2:
            return "east"
        elif r1 == r2 and c1 - 1 == c2:
            return "west"
        elif c1 == c2 and r1 + 1 == r2:
            return "south"
        elif c1 == c2 and r1 - 1 == r2:
            return "north"
        else:
            raise ValueError(f"Invalid move from {pos1} to {pos2}")

    def turn_command(self, current_dir, next_dir):
       directions = ["north", "east", "south", "west"]
       cur   = directions.index(current_dir)
       nxt   = directions.index(next_dir)
       # delta: -2,-1,0,1 중 하나 → 곱하기 90으로 각도 계산
       delta = ((nxt - cur + 2) % 4) - 2
       angle = delta * 90
       return f"R{angle}"


    def distance_between(self, pos1, pos2):
        """
        두 좌표 간의 거리를 계산합니다.
        """
        r1, c1 = pos1
        r2, c2 = pos2
        grid_dist = abs(r1 - r2) + abs(c1 - c2)
        return grid_dist*10

    def convert_command(self, cmd):
        return cmd

    def to_dict(self):
        """
        전체 명령세트를 딕셔너리 형태로 반환합니다.
        """
        structured = []
        for cmd in self.commands:
            # D30, R90, R-90 등 원본 그대로
            structured.append({"command": cmd})
        return {
            "robot_id": self.robot_id,
            "command_count": self.command_count,
            "command_set": structured
        }

    @classmethod
    def send_command_sets(cls, command_sets):
        """
        CommandSet 객체 리스트를 받아 MQTT를 통해 전송합니다.
        """
        try:
            client = mqtt.Client()
            client.connect(MQTT_SERVER, MQTT_PORT, 60)

            message = {"commands": [cs.to_dict() for cs in command_sets]}
            payload = json.dumps(message)

            print("전송 모듈 명령 세트:", payload)
            client.publish(TRANSFER_TOPIC, payload)
            time.sleep(1)
            client.disconnect()

        except Exception as e:
            print(f"로봇 통신 실패: {e}")








