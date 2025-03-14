import os
import socket
import threading
import signal
import sys
import numpy as np
import asyncio
import websockets
import json
import time  
from datetime import datetime
from collections import defaultdict
from sklearn.metrics import mean_squared_error
from scipy.spatial import distance
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

################ Parameter Setting #################
TIMEOUT_THRESHOLD = 2.0     # 일정 시간이 지나면 값을 0으로 설정하기 위한 상수 (default: 2초)
SAVE_EST_KEYPOINTS_DATA = False   # 추정한 3D pose 값을 저장할지 여부 (defalut=False)
CAMERA_P_MATRIX = "UNITY"   # "UNITY" (함수이용 자동추출, default) or "EST" (사진찍어 추정)
image_width = 1920          # 1920 or 1280
image_height = 1080         # 1080 or 720
NUM_JOINTS = 15             # 추정 관절 개수
CAMERA_NAMES = ["Camera1", "Camera2", "Camera3", "Camera4"]
CAM_DIR = os.path.join("..", "HkPose3D_Unity", "Captures")  # 3D pose의 GT값을 가져오거나 EST값을 저장하기 위한 Unity 소스 폴더
GT_DIR = os.path.join(CAM_DIR, "BodyPos3dGT")       # 저장되있는 3D pose의 GT값을 가져오는 경로
EST_DIR = os.path.join(CAM_DIR, "BodyPos3dEST")     # 추정한 3D pose 값을 저장하는 경로
os.makedirs(EST_DIR, exist_ok=True)

if len(sys.argv) == 1:
    IP = '127.0.0.1'   # 내 IP 주소 ('192.168.1.69' '192.168.1.74') 
    PORT = 11111
    IP_WS = '127.0.0.1'
    PORT_WS = 12222  # WebSocket server port
elif len(sys.argv) == 5:
    IP = sys.argv[1]       
    PORT = int(sys.argv[2])  
    IP_WS = sys.argv[3] 
    PORT_WS = int(sys.argv[4])  
else:
    print("Usage: python HkPose3D_Server.py <IP> <PORT> <IP_WS> <PORT_WS>")
    print("- Ex1: python HkPose3D_Server.py 127.0.0.1 11111 127.0.0.1 12222")
    print("- Ex2: python HkPose3D_Server.py 192.168.1.72 11111 127.0.0.1 12222")
    sys.exit(1)


# Camera data structure to hold bytes received, elapsed time, and last updated time
camera_data = {
    "Camera1": {"bytes": 0, "elapsed_time": 0.0, "last_received_time": 0},
    "Camera2": {"bytes": 0, "elapsed_time": 0.0, "last_received_time": 0},
    "Camera3": {"bytes": 0, "elapsed_time": 0.0, "last_received_time": 0},
    "Camera4": {"bytes": 0, "elapsed_time": 0.0, "last_received_time": 0},
    "Server": {"bytes": 0, "rmse": 0.0, "last_sent_time": 0}  # 서버의 전송 바이트와 RMSE 및 마지막 전송 시간
}

# Create the Tkinter window and plot
class CameraDataDisplay:
    def __init__(self, root):
        self.root = root
        self.root.title("Server Traffic Monitoring")
        
        # Create a figure for matplotlib
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack()

        # Create a label for current time
        self.time_label = ttk.Label(root, text="", font=("Helvetica", 16))
        self.time_label.pack()

        # Start updating the plot and time
        self.update_plot()

    def update_plot(self):
        current_time = time.time()  # 현재 시간 (초 단위)

        # 수신 데이터가 일정 시간 동안 없으면 0으로 리셋
        for camera in camera_data.keys():
            if camera != "Server":
                # 마지막 수신 후 경과한 시간 계산
                elapsed_since_last_received = current_time - camera_data[camera]["last_received_time"]
                if elapsed_since_last_received > TIMEOUT_THRESHOLD:
                    camera_data[camera]["bytes"] = 0  # 일정 시간 경과 시 수신 데이터 크기를 0으로

        # 서버에서 일정 시간 동안 전송되지 않으면 0으로 리셋
        elapsed_since_last_sent = current_time - camera_data["Server"]["last_sent_time"]
        if elapsed_since_last_sent > TIMEOUT_THRESHOLD:
            camera_data["Server"]["bytes"] = 0  # 일정 시간 경과 시 전송 데이터 크기를 0으로
            camera_data["Server"]["rmse"] = 0  # RMSE도 0으로 리셋

        # Update the bar chart with current camera data
        camera_names = list(camera_data.keys())[:-1]  # Exclude Server from the camera names
        rx_bytes_received = [camera_data[camera]["bytes"] for camera in camera_names]
        elapsed_times = [camera_data[camera]["elapsed_time"] for camera in camera_names]

        # Access the server bytes and rmse from the camera_data dictionary
        server_bytes = camera_data["Server"]["bytes"]
        server_rmse = camera_data["Server"]["rmse"]

        # Clear the plot and draw new bar chart for both Rx and Server data
        self.ax.clear()

        # Plot Rx data (received data) in blue
        bar_width = 0.35
        rx_positions = np.arange(len(camera_names))
        self.ax.bar(rx_positions, rx_bytes_received, width=bar_width, label='Rx Data (bytes)', color='blue')

        # Plot Server data (bytes) in red, as a single bar on the right of the Rx bars
        server_position = [len(camera_names)]  # Place Server bar to the right of all Rx bars
        self.ax.bar(server_position, [server_bytes], width=bar_width, label='Server Data (bytes)', color='red')

        self.ax.set_ylabel("Traffic (bytes)")
        self.ax.set_title("Edge Server Data Monitor (Rx and Tx)")
        self.ax.set_xticks(list(rx_positions) + server_position)  # Include Server bar in x-axis ticks
        self.ax.set_xticklabels(camera_names + ['Server'])  # Label Server bar as "Server"
        self.ax.legend()

        # Display the current time
        display_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=f"Current Time: {display_time}")

        # Add elapsed times as text on the bars (for Rx data)
        for i, elapsed_time in enumerate(elapsed_times):
            self.ax.text(rx_positions[i], rx_bytes_received[i] + 10, f"{elapsed_time:.2f} ms", ha='center')

        # Add RMSE value as text on the Server bar
        self.ax.text(server_position[0], server_bytes + 10, f"RMSE: {server_rmse:.3f} m", ha='center')

        # Redraw the canvas
        self.canvas.draw()

        # Schedule the next update after 1000ms (1 second)
        self.root.after(1000, self.update_plot)

# 수신 시 마지막 시간을 기록하는 함수
def update_camera_data(camera_name, bytes_received, elapsed_time):
    camera_data[camera_name]["bytes"] = bytes_received
    camera_data[camera_name]["elapsed_time"] = elapsed_time
    camera_data[camera_name]["last_received_time"] = time.time()  # 마지막 수신 시간 기록

# 전송 시 마지막 시간을 기록하는 함수
def update_server_data(bytes_sent, rmse):
    camera_data["Server"]["bytes"] = bytes_sent
    camera_data["Server"]["rmse"] = rmse
    camera_data["Server"]["last_sent_time"] = time.time()  # 마지막 전송 시간 기록


########################### 카메라 P matrix 추출 ##############################
def load_camera_matrix(camera_name):
    """Load the camera projection matrix for the given camera."""
    if CAMERA_P_MATRIX == "EST":
        file_path = os.path.join(CAM_DIR, camera_name, "calibration", f"{camera_name}_Pmatrix_Est.txt")
    elif CAMERA_P_MATRIX == "UNITY":
        file_path = os.path.join(CAM_DIR, camera_name, "calibration", f"{camera_name}_Pmatrix_Unity.txt")
    
    if os.path.exists(file_path):
        return np.loadtxt(file_path, delimiter=',')
    print(f"File not found: {file_path}")
    return None

# Load and store the camera matrices
P_list = [load_camera_matrix(camera) for camera in CAMERA_NAMES]


########################### 알고리즘 ##############################
def triangulate_single_point(pos2D_list, P_list):
    """Triangulate a single 3D point from multiple 2D image points and camera matrices."""
    A = np.vstack([
        pos2D_list[i][0] * P_list[i][2, :] - P_list[i][0, :]
        for i in range(len(P_list))
    ] + [
        pos2D_list[i][1] * P_list[i][2, :] - P_list[i][1, :]
        for i in range(len(P_list))
    ])
    
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    return X[:3] / X[3]

# 최적화하여 속도 개선한 것 (Pmatrix가 UNITY것 일때)
def triangulate_single_point_pixel2NDC_fast(points_list, P_list, image_width, image_height):
    """
    Optimized and faster triangulation of a 3D point using normalized device coordinates (NDC) from multiple cameras.
    
    Parameters:
    points_list (list): List of 2D image points for each camera.
    P_list (list): List of camera projection matrices.
    image_width (int): Width of the image in pixels.
    image_height (int): Height of the image in pixels.

    Returns:
    np.array: Estimated 3D world position (1x3 numpy array).
    """
    # Precompute scaling factors for conversion to NDC
    scale_x = 2 / image_width
    scale_y = 2 / image_height

    # Number of cameras (or 2D points)
    num_cameras = len(P_list)

    # Pre-allocate the A matrix (it will have 2 * num_cameras rows and 4 columns)
    A = np.zeros((2 * num_cameras, 4))

    # Vectorized computation of A matrix
    for i in range(num_cameras):
        ndc_point_x = points_list[i][0] * scale_x - 1
        ndc_point_y = 1 - points_list[i][1] * scale_y

        # Extract the projection matrix
        P = P_list[i]

        # First row for the x-coordinate
        A[2 * i] = ndc_point_x * P[2, :] - P[0, :]
        # Second row for the y-coordinate
        A[2 * i + 1] = ndc_point_y * P[2, :] - P[1, :]

    # Perform SVD on A
    _, _, Vt = np.linalg.svd(A, full_matrices=False)

    # The last row of Vt (corresponding to the smallest singular value)
    world_point_homogeneous = Vt[-1]

    # Convert from homogeneous coordinates to 3D coordinates
    world_point = world_point_homogeneous[:3] / world_point_homogeneous[3]

    return world_point


# 관절 쌍 연결 정보 (추가적인 보정을 위한 인접 관절 정의)
PAIRS = [
    (0, 1), (0, 2), # 코 - 눈
    (1, 3), (2, 4), # 눈 - 어깨
    (3, 4),         # 어깨 - 어깨
    (3, 5), (4, 6), # 어깨 - 팔꿈치    
    (5, 7), (6, 8), # 팔꿈치 - 손목
    (9, 10),        # 엉덩이 - 엉덩이
    (3, 9), (4, 10), # 어깨 - 엉덩이
    (9, 11), (10, 12), # 엉덩이 - 무릎
    (11, 13), (12, 14)  # 무릎 - 발목
]

# 추정한 관절 값들의 이상치 탐지 및 보정을 위한 mahalanobis 알고리즘
def mahalanobis_outlier_detection(keypoints_3D, threshold=3.0):
    # 각 관절의 3D 좌표에 대한 평균과 공분산 계산
    mean = np.mean(keypoints_3D, axis=0)
    cov = np.cov(keypoints_3D, rowvar=False)
    inv_covmat = np.linalg.inv(cov)
    
    # Mahalanobis Distance 계산
    distances = [distance.mahalanobis(point, mean, inv_covmat) for point in keypoints_3D]
    
    # 이상치 탐지 및 보정
    corrected_keypoints_3D = keypoints_3D.copy()
    for i, dist in enumerate(distances):
        if dist > threshold:  # threshold가 작을 수록 이상치로 감지되는 관절 수 증가
            print(f"Outlier detected at joint {i} with Mahalanobis distance {dist:.2f}")
            # 보정 방법: 인접 관절의 평균 위치로 대체
            neighbors = [pair[1] if pair[0] == i else pair[0] for pair in PAIRS if i in pair]
            corrected_keypoints_3D[i] = np.mean(keypoints_3D[neighbors], axis=0)
    
    return corrected_keypoints_3D

# 이벤트 검출 알고리즘
def is_fall_or_jump(keypoints, fall_threshold=0.2, jump_threshold=2.0):
    """
    Detects whether a fall-down or jump event has occurred.

    Args:
        keypoints: List of 3D keypoint coordinates [(x, y, z), ...].
        fall_threshold: Y-axis difference threshold for fall detection.
        jump_threshold: Z-axis height threshold for jump detection.

    Returns:
        str: "Fall-down", "Jump", or "None" depending on the detected event.
    """
    def avg_y(a, b):
        return (a[1] + b[1]) / 2

    # Necessary joint indices
    left_hip, right_hip = keypoints[9], keypoints[10]
    left_shoulder, right_shoulder = keypoints[3], keypoints[4]
    left_ankle, right_ankle = keypoints[13], keypoints[14]
    nose = keypoints[0]

    # Calculate average y-coordinates
    hip_y = avg_y(left_hip, right_hip)
    shoulder_y = avg_y(left_shoulder, right_shoulder)
    ankle_y = avg_y(left_ankle, right_ankle)

    # Check for jump condition
    if nose[1] >= jump_threshold:
        return "Jump"

    # Check for fall-down condition
    if abs(shoulder_y - hip_y) <= fall_threshold or abs(hip_y - ankle_y) <= fall_threshold:
        return "Fall-down"

    return "None"


######### Device로 부터 받은 데이터 저장/처리리 구조체 #########
class KeypointsData:
    def __init__(self):
        self.data = defaultdict(lambda: defaultdict(list))
        self.current_timestamp = None

    def add_data(self, camera_name, timestamp, keypoints):
        if self.current_timestamp is None:
            self.current_timestamp = timestamp

        if timestamp > self.current_timestamp:
            asyncio.run(self.process_and_reset())
            self.current_timestamp = timestamp

        self.data[timestamp][camera_name].extend(keypoints)

    async def process_and_reset(self):
        if self.current_timestamp is not None:
            # keypoints 정보를 가지고 있는 카메라의 수를 계산
            num_keypoints = len([camera for camera in CAMERA_NAMES if camera in self.data[self.current_timestamp]])
            print(f"Triangulate with \033[93m{num_keypoints} keypoints\033[0m of {self.current_timestamp}")

            if num_keypoints > 1:
                start_time_est = time.time()

                # 각 카메라의 keypoints를 pos2D_dict에 저장
                pos2D_dict = {
                    camera: np.array([
                        [kp[0], kp[1]]  # (x, y) 좌표만 추출
                        for kp in self.data[self.current_timestamp][camera]
                    ])
                    for camera in CAMERA_NAMES if camera in self.data[self.current_timestamp]
                }

                # 3D point estimation
                pos3D_est = np.zeros((NUM_JOINTS, 3))
                for joint_idx in range(NUM_JOINTS):  # 각 관절별로 하나씩
                    valid_pos2D_list = []
                    valid_P_list = []

                    for camera in CAMERA_NAMES:
                        if camera in pos2D_dict and not np.all(pos2D_dict[camera][joint_idx] == 0):
                            valid_pos2D_list.append(pos2D_dict[camera][joint_idx])
                            valid_P_list.append(P_list[CAMERA_NAMES.index(camera)])

                    if len(valid_pos2D_list) > 1:
                        if CAMERA_P_MATRIX == "EST":
                            pos3D_est[joint_idx] = triangulate_single_point(valid_pos2D_list, valid_P_list)
                        elif CAMERA_P_MATRIX == "UNITY":
                            pos3D_est[joint_idx] = triangulate_single_point_pixel2NDC_fast(valid_pos2D_list, valid_P_list, image_width, image_height)
                    else:
                        pos3D_est[joint_idx] = [0, 0, 0]

                # 이상치 감지 및 수정 실행
                corrected_pos3D_est = mahalanobis_outlier_detection(pos3D_est)
                print(f"- Processing time for 3D pose estimation: {(time.time() - start_time_est) * 1000:.6f} ms")

                # 성능 측정 및 결과 계산 함수 호출
                await self.evaluate_results(corrected_pos3D_est)

        # 데이터 초기화
        self.data.clear()

    async def evaluate_results(self, corrected_pos3D_est):
        """MSE, RMSE, Delay 계산 및 WebSocket으로 데이터 전송."""        
        # 기본값 설정 (예: rmse와 captureTime의 기본값)
        rmse = 0  # 기본값
        captureTime = "0000-00-00_00-00-00.000"  # 기본 포맷
        event_name = "None"  # Default 이벤트 이름
            
        start_time_result = time.time()

        # Detect events (fall-down or jump)
        event_name = is_fall_or_jump(corrected_pos3D_est)
        if event_name == "Fall-down":
            print(f"\033[92mFall-down Detected!!\033[0m")
        elif event_name == "Jump":
            print(f"\033[93mJump Detected!!\033[0m")

        # 파일 경로 로드
        load_path = os.path.join(GT_DIR, f"body_pos3D_{self.current_timestamp}.txt")
        if os.path.exists(load_path):
            # 텍스트 파일의 모든 줄을 읽어들임
            with open(load_path, 'r') as f:
                lines = f.readlines()

            # 마지막 줄의 datetime 정보 추출
            captureTime = lines[-1].strip()  # 마지막 줄에서 개행 문자 제거
            e2eDelay = time.time() - datetime.strptime(captureTime, '%Y-%m-%d_%H-%M-%S.%f').timestamp()

            # 나머지 줄을 points_gt로 처리
            points_gt = np.loadtxt(lines[:-1], delimiter=',')

            # MSE와 RMSE 계산
            mse = mean_squared_error(corrected_pos3D_est, points_gt)
            rmse = np.sqrt(mse)
            print(f"\033[93mMSE: {mse:.6f}, RMSE: {rmse:.6f} meters / Capture time: {captureTime}, Elapsed {e2eDelay:.6f} seconds\033[0m")
        else:
            print(f"Warning: File not found at {load_path}. MSE & RMSE cannot be calculated!")

        print(f"- Processing time for result calculation: {(time.time() - start_time_result) * 1000:.6f} ms")


        # 3D keypoints 별도 저장 (SAVE_EST_KEYPOINTS_DATA가 True일 때만)
        if SAVE_EST_KEYPOINTS_DATA:
            save_path = os.path.join(EST_DIR, f"BodyPos3dEST_{self.current_timestamp}.txt")
            with open(save_path, 'w') as f:
                # Corrected 3D keypoints 저장
                for joint in corrected_pos3D_est:
                    f.write(f"{joint[0]:.6f}, {joint[1]:.6f}, {joint[2]:.6f}\n")
                # 추가 정보 저장
                f.write(f"{captureTime}\n")  # 16번째 행: captureTime
                f.write(f"{rmse:.6f}\n")     # 17번째 행: RMSE
                f.write(f"{event_name}\n")   # 18번째 행: Event name
            print(f"\033[96mCorrected 3D data saved to {save_path}\033[0m")
            
        # WebSocket 클라이언트로 3D 데이터 전송
        await self.send_pos3D_to_clients(corrected_pos3D_est, rmse, captureTime, event_name)
    
    async def send_pos3D_to_clients(self, corrected_pos3D_est, rmse, captureTime, event_name):
        """WebSocket 클라이언트로 3D 포인트 데이터, RMSE, 및 Capture Time을 JSON 형태로 전송."""
        if connected_websockets:
            # 3D 포인트 데이터를 JSON으로 생성
            pos3D_data = [{"x": round(joint[0], 3), "y": round(joint[1], 3), "z": round(joint[2], 3)} for joint in corrected_pos3D_est]

            # 전송할 JSON 메시지 생성
            message = {
                "3D_points": pos3D_data,
                "rmse": rmse,
                "capture_time": captureTime,
                "event_name": event_name
            }

            # JSON 메시지를 문자열로 변환
            message_json = json.dumps(message)

            # WebSocket으로 전송
            for websocket in connected_websockets:
                try:
                    await websocket.send(message_json + '\n')
                    currTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"\033[91mSent 3D pos data {len(message_json)} bytes to WebSocket client at {currTime}\n\033[0m")

                    # 서버 데이터 업데이트 (전송 바이트 및 RMSE 값)
                    update_server_data(len(message_json), rmse)
                except Exception as e:
                    print(f"Error sending data to WebSocket client: {e}")

keypoints_data_manager = KeypointsData()


############ Device로 부터 받은 데이터 처리 #############
def handle_client(client_socket, client_address):
    """클라이언트의 데이터를 처리하는 함수."""
    print(f"클라이언트 {client_address} 가 접속했습니다.")
    try:
        while True:
            try:
                # data = client_socket.recv(1024)

                # 먼저 데이터 크기(4바이트)를 수신
                data_length_bytes = client_socket.recv(4)
                if not data_length_bytes:
                    print("data_length 수신 실패")
                    break
                data_length = int.from_bytes(data_length_bytes, byteorder='big')

                # 그다음 데이터 길이만큼 수신
                data = b''
                while len(data) < data_length:
                    chunk = client_socket.recv(1024)
                    if not chunk:
                        break
                    data += chunk          
                if not data:
                    break  # 데이터가 없으면 루프 탈출

                # 수신한 데이터를 처리 (JSON 형식 디코딩)
                data_str = data.decode('utf-8')
                try:
                    # JSON 파싱
                    received_json = json.loads(data_str)
                    camera_name = received_json.get('camera_name')
                    exact_timestamp = received_json.get('exact_timestamp')
                    slotted_timestamp = received_json.get('slotted_timestamp')
                    keypoints_data_list = received_json.get('keypoints')

                    elapsed_time = time.time() - datetime.strptime(exact_timestamp, '%Y-%m-%d_%H-%M-%S.%f').timestamp()
                    print(f"Received {len(data)} bytes from {camera_name} ({slotted_timestamp}, {exact_timestamp}) / Elapsed {elapsed_time*1000:.6f} ms")

                    # 카메라 데이터 업데이트
                    update_camera_data(camera_name, len(data), elapsed_time * 1000)

                    # keypoints_data_list는 1차원 배열이므로, 3개의 좌표(x, y, z)씩 묶어서 처리
                    keypoints_data = []
                    for i in range(0, len(keypoints_data_list), 3):
                        x, y, z = keypoints_data_list[i:i + 3]
                        keypoints_data.append((x, y, z))                    
                    # print(f"Processed keypoints: {keypoints_data}")

                    # keypoints_data 추가 (사용자 정의 처리 함수로 전달)
                    keypoints_data_manager.add_data(camera_name, slotted_timestamp, keypoints_data)
                
                except json.JSONDecodeError as e:
                    print(f"JSON 디코딩 오류 발생: {e}")
                    continue
            except OSError as e:
                print(f"데이터 수신 중 오류 발생: {e}")
                break        

    finally:
        client_socket.close()
        print(f"클라이언트 {client_address} 연결이 종료되었습니다.")


######################## Server Socket ######################## 
server_socket = None
connected_websockets = set()

def start_server():
    """서버를 시작하고 클라이언트 연결을 처리하는 함수."""
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((IP, PORT))
    server_socket.listen(5)
    print(f"Edge Server: {IP}:{PORT}에서 클라이언트의 접속을 기다리는 중...")

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            client_handler = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address)
            )
            client_handler.start()
    except KeyboardInterrupt:
        print("\n서버가 종료 중입니다...")
    finally:
        server_socket.close()
        print("서버가 완전히 종료되었습니다.")

def signal_handler(sig, frame):
    """Ctrl+C 신호를 처리하는 함수."""
    print("\nCtrl+C 신호가 감지되었습니다. 서버를 종료합니다...")
    if server_socket:
        server_socket.close()
    sys.exit(0)

# SIGINT 신호에 대한 핸들러 설정
signal.signal(signal.SIGINT, signal_handler)


######################## WebSocket Server ########################
async def handle_websocket(websocket, path):
    """Handles new WebSocket connections."""
    # WebSocket의 기본 TCP 소켓 설정
    raw_socket = websocket.transport.get_extra_info("socket")
    if raw_socket:
        raw_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # TCP_NODELAY 활성화
        print("TCP_NODELAY 설정이 완료되었습니다.")

    connected_websockets.add(websocket)
    print(f"New WebSocket client connected: {path}")
    try:
        await websocket.wait_closed()
    finally:
        connected_websockets.remove(websocket)
        print("WebSocket client disconnected")

async def start_websocket_server():
    """Starts the WebSocket server."""
    async with websockets.serve(handle_websocket, IP_WS, PORT_WS):
        print(f"WebSocket server started on ws://{IP_WS}:{PORT_WS}")
        await asyncio.Future()  # Keep the server running


# # 서버 시작
# if __name__ == "__main__":
#     threading.Thread(target=start_gui).start()  # Start the GUI in a separate thread
#     threading.Thread(target=start_server).start()  # Start TCP server in a new thread
#     asyncio.run(start_websocket_server())  # Run WebSocket server

# # Function to start the GUI in a separate thread
# def start_gui():
#     root = tk.Tk()
#     app = CameraDataDisplay(root)
#     root.mainloop()

# Main function to start the GUI and other servers
def main():
    # Start the GUI in the main thread
    root = tk.Tk()
    app = CameraDataDisplay(root)

    # Start the TCP server in a separate thread
    threading.Thread(target=start_server, daemon=True).start()

    # Start the WebSocket server in a separate thread
    threading.Thread(target=lambda: asyncio.run(start_websocket_server()), daemon=True).start()

    # Start the Tkinter mainloop
    root.mainloop()

if __name__ == "__main__":
    main()