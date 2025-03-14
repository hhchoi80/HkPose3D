using UnityEngine;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Diagnostics;
using Debug = UnityEngine.Debug;
using System;
using Newtonsoft.Json;

public class CameraCapture : MonoBehaviour
{
    [SerializeField][Tooltip("Edge device's IP address")]
    private string HOST = "127.0.0.1";    // 서버 주소 (127.0.0.1, 192.168.1.69, 192.168.1.74)
    [SerializeField][Tooltip("Edge device's Port number")]
    private int PORT = 10000;            // 서버 포트 (10000 + 카메라번호)
    [SerializeField][Tooltip("Width of the image to be captured")]
    private int width = 1920; // 캡처할 이미지의 너비 FHD:1920 x 1080 , HD: 1280 x 720
    [SerializeField][Tooltip("Height of the image to be captured")]
    private int height = 1080; // 캡처할 이미지의 높이 1080
    [SerializeField][Tooltip("Enable captureing of image")]
    private bool captureEnabled = false; // 캡처 활성화 여부를 결정하는 체크박스
    [SerializeField][Tooltip("Capture interval (second)")]
    private float captureInterval = 0.5f;      // 캡처 간격 
    [SerializeField][Tooltip("Enable sending of captured image")]
    private bool sendEnabled = false; // 데이터 전송 활성화 여부
    [SerializeField][Tooltip("Enable saving of captured image files")]
    private bool fileSaveEnabled = false; // 파일 저장 활성화 여부
        
    private string folderPath; // 이미지를 저장할 폴더 경로
    private RenderTexture rt;
    private Texture2D screenShot;
    private Camera cam; // 대상 카메라
    private float captureTimer = 0f; // 타이머 변수
    private TcpClient client;   // TCP 클라이언트와 스트림 선언
    private NetworkStream stream;

    // Start is called before the first frame update
    void Start()
    {
        // 스크립트가 붙어 있는 오브젝트에서 카메라 컴포넌트를 찾아 할당
        cam = GetComponent<Camera>();

        if (cam != null) // Camera 컴포넌트가 실제로 존재하는지 확인
        {
            // 카메라의 위치 좌표를 콘솔에 출력
            Vector3 camPosition = cam.transform.position;
            Debug.Log(string.Format("{0} Position: x={1}, y={2}, z={3}", cam.gameObject.name, camPosition.x, camPosition.y, camPosition.z));
            Quaternion camRotation = cam.transform.rotation;

            // Calculate the view matrix            
            Matrix4x4 viewMatrix = cam.worldToCameraMatrix;
            Debug.Log(string.Format("{0} View Matrix: {1}", cam.gameObject.name, MatrixToString(viewMatrix)));

            // Get the camera's projection matrix
            Matrix4x4 projectionMatrix = cam.projectionMatrix;
            Debug.Log(string.Format("{0} Projection Matrix: {1}", cam.gameObject.name, MatrixToString(projectionMatrix)));

            // Combine the view and projection matrices
            Matrix4x4 viewProjectionMatrix = projectionMatrix * viewMatrix;
            Debug.Log(string.Format("{0} ViewProjection Matrix: {1}", cam.gameObject.name, MatrixToString(viewProjectionMatrix)));

            // Unity로 부터 구한 카메라 P matrix를 파일로 저장
            string folderPath2 = string.Format("Captures/{0}/calibration", cam.gameObject.name);
            if (!Directory.Exists(folderPath2))
            {
                Directory.CreateDirectory(folderPath2);  // 저장 폴더 생성
            }
            string fileName = string.Format("{0}/{1}_Pmatrix_Unity.txt", folderPath2, cam.gameObject.name);
            File.WriteAllText(fileName, MatrixToString(viewProjectionMatrix));


            // 예시 3D 월드 좌표
            Vector3 worldPosition = new Vector3(0, 0, 0);

            // Homogeneous coordinates (4D vector for projection)
            Vector4 homogenousPosition = new Vector4(worldPosition.x, worldPosition.y, worldPosition.z, 1.0f);

            // 클립 공간 좌표로 변환
            Vector4 clipSpacePosition = viewProjectionMatrix * homogenousPosition;

            // NDC 공간으로 변환 (투영 나눗셈)
            Vector3 ndcPosition = new Vector3(
                clipSpacePosition.x / clipSpacePosition.w,
                clipSpacePosition.y / clipSpacePosition.w,
                clipSpacePosition.z / clipSpacePosition.w
            );

            // NDC 공간에서 이미지 평면의 픽셀 좌표로 변환
            Vector2 pixelPosition = new Vector2(
                (ndcPosition.x + 1) * 0.5f * width,
                (1 - ndcPosition.y) * 0.5f * height
            );
            // 결과 출력
            Debug.Log(string.Format("{0} Pixel Position: {1}", cam.gameObject.name, pixelPosition));

            // RenderTexture 초기화
            rt = new RenderTexture(width, height, 24);
            screenShot = new Texture2D(width, height, TextureFormat.RGB24, false);

            // folderPath를 카메라 오브젝트의 이름을 포함하여 설정         
            if (fileSaveEnabled)
            {                   
                folderPath = string.Format("Captures/{0}", cam.gameObject.name);
                if (!Directory.Exists(folderPath))
                {
                    Directory.CreateDirectory(folderPath);  // 저장 폴더 생성
                }
            }

            // TCP 클라이언트 생성 및 서버 연결            
            if (sendEnabled)
            {
                PORT = PORT + int.Parse(cam.gameObject.name.Substring("Camera".Length)); // Camera 번호 추출
                try
                {
                    client = new TcpClient(HOST, PORT);     
                    stream = client.GetStream();
                }
                catch (System.Exception e)
                {
                    Debug.LogError($"{cam.gameObject.name}이 서버 {HOST}:{PORT}에 연결할 수 없습니다: {e.Message}");
                }                
            }            
        }
        else
        {
            Debug.LogError("Camera component not found on the GameObject.");
        }
    }

    // LateUpdate is called once per frame, after Update has finished 
    void LateUpdate()
    {
        if (captureEnabled && cam != null)
        {
            captureTimer += Time.deltaTime;

            // captureInterval 간격으로 캡처를 수행
            if (captureTimer >= captureInterval)
            {
                captureTimer = 0f; // 타이머 초기화

                // RenderTexture를 현재 카메라의 출력 대상으로 임시 설정
                cam.targetTexture = rt;
                cam.Render();

                // RenderTexture를 현재 렌더링 대상으로 설정하여 캡처
                RenderTexture.active = rt;
                screenShot.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                screenShot.Apply();

                // 캡처 완료 후 RenderTexture 설정 해제
                cam.targetTexture = null;
                RenderTexture.active = null;

                // 이미지 파일로 변환
                byte[] imageData = screenShot.EncodeToJPG();
                
                DateTime currTime = System.DateTime.Now;
                string exactTimeStamp = currTime.ToString("yyyy-MM-dd_HH-mm-ss.fff");
                string slottedMilliseconds = currTime.Millisecond < (captureInterval*1000) ? "0" : "5";
                string slottedTimeStamp = currTime.ToString("yyyy-MM-dd_HH-mm-ss") + "." + slottedMilliseconds;                

                if (sendEnabled && stream != null && client.Connected)
                {
                    // 전송 데이터(dataToSend) 생성 //////////////////////////
                    var headerObject = new
                    {
                        CameraName = cam.gameObject.name,
                        ExactTimeStamp = exactTimeStamp,
                        SlottedTimeStamp = slottedTimeStamp,
                        ImageDataLength = imageData.Length
                    };
                    // JSON 형식으로 헤더 직렬화
                    string headerJson = JsonConvert.SerializeObject(headerObject);
                    byte[] headerBytes = Encoding.UTF8.GetBytes(headerJson);
                    byte[] headerLengthBytes = BitConverter.GetBytes(headerBytes.Length);       // 헤더 길이 (4바이트, little-endian)    
                    byte[] dataToSend = new byte[headerLengthBytes.Length + headerBytes.Length + imageData.Length]; // 최종 전송 데이터 할당
                    // 헤더 길이, 헤더, 이미지 데이터 순서대로 복사
                    headerLengthBytes.CopyTo(dataToSend, 0);
                    headerBytes.CopyTo(dataToSend, headerLengthBytes.Length);
                    imageData.CopyTo(dataToSend, headerLengthBytes.Length + headerBytes.Length);

                    try
                    {
                        stream.Write(dataToSend, 0, dataToSend.Length);
                    }
                    catch (System.Exception e)
                    {
                        Debug.LogError($"데이터 전송 중 오류 발생: {e.Message}");
                    }

                    Debug.Log($"{cam.gameObject.name} sents data ({dataToSend.Length} B = Header {headerBytes.Length} + Image {imageData.Length}) at {exactTimeStamp} to the server {HOST}:{PORT}.");                    
                }

                if (fileSaveEnabled)
                {
                    Stopwatch stopwatch = Stopwatch.StartNew();
                    string fileName = string.Format("{0}/{1}_ScreenShot_{2}.jpg", folderPath, cam.gameObject.name, slottedTimeStamp);
                    File.WriteAllBytes(fileName, imageData);
                    stopwatch.Stop();
                    Debug.Log(string.Format("Saved ScreenShot to {0}. Time taken: {1} ms", fileName, stopwatch.Elapsed.TotalMilliseconds));
                }
            }
        }
    }

    void OnGUI()
    {
        // 캡처 활성화 여부를 체크박스로 설정할 수 있는 UI
        captureEnabled = GUI.Toggle(new Rect(10, 10, 200, 30), captureEnabled, "Enable Capture");
    }

    void OnDestroy()
    {
        // 자원 정리
        if (rt)
        {
            Destroy(rt);
        }
    }

    // 행렬을 문자열로 변환하는 함수
    string MatrixToString(Matrix4x4 matrix)
    {
        return string.Format("{0}, {1}, {2}, {3}\n{4}, {5}, {6}, {7}\n{8}, {9}, {10}, {11}\n{12}, {13}, {14}, {15}",
            matrix[0, 0], matrix[0, 1], matrix[0, 2], matrix[0, 3],
            matrix[1, 0], matrix[1, 1], matrix[1, 2], matrix[1, 3],
            matrix[2, 0], matrix[2, 1], matrix[2, 2], matrix[2, 3],
            matrix[3, 0], matrix[3, 1], matrix[3, 2], matrix[3, 3]);
    }
}
