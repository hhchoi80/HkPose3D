import json
import os
import socket
import threading
import sys
import asyncio
import websockets
import queue
from ultralytics import YOLO
from io import BytesIO
from PIL import Image

############ Parameter Setting #############
SAVE_KEYPOINT_IMAGE = False     # 2D Pose estimation한 이미지의 저장 여부 (default=False)
SAVE_KEYPOINTS_DATA = False     # 2D Pose estimation한 결과 데이터 저장 여부 (default=False)
BASE_DIR = "Result"
EXCLUDED_KEYPOINTS = [3, 4]  # Indices of keypoints to exclude
MAX_QUEUE_SIZE = 5  # 최대 대기열 크기

HOST = '127.0.0.1'
PORT = 10001
PORT_WS = 20001
HOST_SERV = '127.0.0.1'
PORT_SERV = 11111

websocket_client = None  # WebSocket 클라이언트는 1개만 있다고 가정
edge_socket = None
ws_loop = None
image_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)  # YOLO 처리 스레드로 전달할 이미지 대기열

# 명령줄 인자 처리
if len(sys.argv) == 6:
    HOST = sys.argv[1]       
    PORT = int(sys.argv[2])  
    PORT_WS = int(sys.argv[3])
    HOST_SERV = sys.argv[4] 
    PORT_SERV = int(sys.argv[5])      
else:
    print("Usage: python HkPose3D_Device.py <MY_IP> <PORT> <PORT_WS> <SERVER_IP> <SERVER_PORT>")
    print("- Ex1: python HkPose3D_Device.py 127.0.0.1 10001 20001 127.0.0.1 11111 (포트번호는 하나씩 더해줘야)")
    print("- Ex2: python HkPose3D_Device.py 192.168.1.75 10001 20001 192.168.1.72 11111 (포트번호는 하나씩 더해줘야)")
    sys.exit(1)

# WebSocket server
async def websocket_handler(websocket, path):
    global websocket_client
    print("New WebSocket client connected.")
    websocket_client = websocket
    try:
        async for _ in websocket:
            pass
    except websockets.ConnectionClosed:
        print("WebSocket client disconnected.")
    finally:
        websocket_client = None

async def start_websocket_server():
    async with websockets.serve(websocket_handler, HOST, PORT_WS):
        print(f"WebSocket server started on ws://{HOST}:{PORT_WS}")
        await asyncio.Future()  # 서버가 계속 실행되도록 대기

# WebSocket 전송 처리
async def send_image_to_websocket(image_data):
    global websocket_client
    if websocket_client:
        try:
            await websocket_client.send(image_data)  # 비동기적으로 이미지 전송
            print(f"\033[92mSent image data ({len(image_data)} bytes) to WebSocket client.\033[0m")
        except websockets.ConnectionClosed:
            print("WebSocket client connection closed.")
        except Exception as e:
            print(f"Failed to send image data: {e}")
    else:
        print("No WebSocket client connected.")

# WebSocket 서버 중지
def stop_websocket_server():
    global ws_loop
    print("Shutting down WebSocket server...")
    if ws_loop:
        for task in asyncio.all_tasks(ws_loop):
            task.cancel()  # asyncio에서 실행 중인 모든 작업 취소
        ws_loop.stop()
    print("WebSocket server shut down.")


# Helper functions
def create_directory(camera_name):
    directory = os.path.join(BASE_DIR, camera_name)
    os.makedirs(directory, exist_ok=True)
    return directory

def save_keypoint_image(result, camera_name, timestamp):
    directory = create_directory(camera_name)
    filepath = os.path.join(directory, f"{camera_name}_{timestamp}.jpg")
    result.save(filename=filepath)
    print(f"Keypoint image saved as {filepath}")

def save_keypoints_data(keypoints, camera_name, timestamp):
    directory = create_directory(camera_name)
    filepath = os.path.join(directory, f"{camera_name}_{timestamp}.txt")
    with open(filepath, "w") as f:
        for i, kp in enumerate(keypoints.data[0]):
            if i not in EXCLUDED_KEYPOINTS:
                x, y, z = kp.tolist()
                f.write(f"{x}, {y}, {z}\n")
    print(f"Keypoints data saved as {filepath}")

def send_keypoints_data(keypoints, camera_name, slotted_timestamp, exact_timestamp):
    global edge_socket
    try:
        if edge_socket is None:
            edge_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            edge_socket.settimeout(5)  # 5초 타임아웃
            edge_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 소켓 재사용 설정
            edge_socket.connect((HOST_SERV, PORT_SERV))
            print(f"Connected to keypoints data server at {HOST_SERV}:{PORT_SERV}")

        keypoints_array = keypoints.data[0].cpu().numpy()
        keypoints_filtered = [
            round(float(coord), 3) for i, kp in enumerate(keypoints_array) if i not in EXCLUDED_KEYPOINTS for coord in kp
        ]

        data_json = {
            "camera_name": camera_name,
            "exact_timestamp": exact_timestamp,
            "slotted_timestamp": slotted_timestamp,
            "keypoints": keypoints_filtered
        }

        data_bytes = json.dumps(data_json).encode('utf-8')
        data_length = len(data_bytes)
        data_to_send = data_length.to_bytes(4, byteorder='big') + data_bytes

        edge_socket.sendall(data_to_send)
        print(f"\033[91mSent 2D pos data ({len(data_bytes)} bytes) to {HOST_SERV}:{PORT_SERV}.\033[0m")

    except socket.timeout:
        print("Socket timeout occurred. Retrying connection...")
        edge_socket.close()
        edge_socket = None  # 소켓 재연결 준비

    except (ConnectionResetError, ConnectionAbortedError):
        print("Connection reset by peer or aborted. Resetting socket...")
        edge_socket.close()
        edge_socket = None  # 소켓 재연결 준비

    except Exception as e:
        print(f"Failed to send 2D pos data: {e}")
        if edge_socket:
            edge_socket.close()
            edge_socket = None  # 소켓 재연결 준비


# YOLO 처리 스레드 (하나의 스레드만 실행됨)
def yolo_processing_thread():
    while True:
        # 이미지 대기열에서 이미지 가져오기 (대기)
        image_data, camera_name, slotted_timestamp, exact_timestamp = image_queue.get()
        print(f"Processing image. Queue size: {image_queue.qsize()}")

        image = Image.open(BytesIO(image_data))
        results = model(image)
        print(f"YOLO processing complete for {camera_name}.")

        for result in results:
            keypoints = result.keypoints
            if SAVE_KEYPOINT_IMAGE:
                save_keypoint_image(result, camera_name, slotted_timestamp)
            if SAVE_KEYPOINTS_DATA:
                save_keypoints_data(keypoints, camera_name, slotted_timestamp)
            if keypoints.has_visible:   # has_visible이 True로 검출된 경우만 전송
                send_keypoints_data(keypoints, camera_name, slotted_timestamp, exact_timestamp)

def process_in_thread(image_data, camera_name, slotted_timestamp, exact_timestamp):
    # 이미지 대기열에 데이터 추가 (최대 크기 초과 시 대기열 비우고 새로 추가)
    if image_queue.qsize() >= MAX_QUEUE_SIZE:
        print("\033[93mQueue full. Clearing queue and adding new image.\033[0m")  # 노란색 출력
        while not image_queue.empty():
            image_queue.get()  # 기존 대기열의 모든 항목 제거
    image_queue.put((image_data, camera_name, slotted_timestamp, exact_timestamp))
    print(f"Image added to queue. Queue size: {image_queue.qsize()}")


def recv_exactly(sock, n):
    """ 정확히 n바이트를 수신하는 함수 """
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection lost while receiving data.")
        data += chunk
    return data


# Main execution starts here
if __name__ == "__main__":
    # YOLO model loading
    print("YOLO model loading...")
    model = YOLO("yolov8n-pose.pt") # YOLOv8 pose nano 모델 사용용
    results = model("warmup.jpg")   # 사전에 임의 이미지로 yolo 준비시킴킴
    print("YOLO model loaded")

    # Start WebSocket server in a separate thread
    websocket_thread = threading.Thread(target=lambda: asyncio.run(start_websocket_server()))
    websocket_thread.start()

    # YOLO 처리 스레드 시작 (하나만 생성)
    yolo_thread = threading.Thread(target=yolo_processing_thread, daemon=True)
    yolo_thread.start()

    # Start TCP server
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)
    print(f"Camera server started at {HOST}:{PORT}")

    client_socket, client_address = server_socket.accept()
    print(f"Client {client_address} connected.")

    try:
        while True:        
            # 정확히 4바이트를 읽어서 헤더 길이 추출
            header_length_bytes = recv_exactly(client_socket, 4)
            header_length = int.from_bytes(header_length_bytes, byteorder='little')
            
            # 헤더 길이 검증
            if header_length <= 0 or header_length > 1024:
                print(f"Invalid header length: {header_length}")
                continue

            # 정확히 header_length 바이트만큼 헤더 수신
            header_data = recv_exactly(client_socket, header_length)
            header_json = header_data.decode('utf-8')
            header = json.loads(header_json)

            # 헤더에서 필요한 정보 추출
            camera_name = header.get('CameraName')
            exact_timestamp = header.get('ExactTimeStamp')
            slotted_timestamp = header.get('SlottedTimeStamp')
            image_data_length = header.get('ImageDataLength')

            # 이미지 데이터 정확히 수신
            image_data = recv_exactly(client_socket, image_data_length)

            print(f"Received data from {camera_name} with timestamps {exact_timestamp}, {slotted_timestamp}")

            if websocket_client:
                print("WebSocket clients detected. Sending image directly to WebSocket.")                
                asyncio.run(send_image_to_websocket(image_data))
            else:
                process_in_thread(image_data, camera_name, slotted_timestamp, exact_timestamp)

            if image_data == b'close_connection':
                print("Client disconnected.")
                break
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        stop_websocket_server()
        if edge_socket:
            edge_socket.close()
        client_socket.close()
        server_socket.close()
        print("Server shut down.")
        os._exit(0)  # 강제로 프로그램 종료
