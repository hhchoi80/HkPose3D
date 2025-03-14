let socketWorker = new Worker("/js/messageWorker.js");
let latestMessage = null; // 최신 메시지 저장 변수

window.GetPose3D = (canvasId, ip, port) => {
    console.log(`[HHCHOI] Connect request to ${ip} on port ${port}!!`);

    // 기본 설정
    const canvas = document.getElementById(canvasId);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
    camera.position.set(0, 5, 5);

    const renderer = new THREE.WebGLRenderer({ canvas });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.setClearColor(0xd3d3d3, 1);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.update();

    // 관절 설정
    const createJointMaterial = (color) => new THREE.MeshBasicMaterial({ color });
    const jointGeometry = new THREE.SphereGeometry(0.05, 20, 20);

    const jointColors = [
        0x00ff00, 0x00ff00, 0x00ff00, // Green: 0, 1, 2
        0x0000ff, 0x0000ff, 0x0000ff, // Blue: 3, 4, 5
        0x0000ff, 0x0000ff, 0x0000ff, // Blue: 6, 7, 8
        0xff0000, 0xff0000, 0xff0000, // Red: 9, 10, 11
        0xff0000, 0xff0000, 0xff0000  // Red: 12, 13, 14
    ];

    const jointMeshes = jointColors.map((color) => {
        const mesh = new THREE.Mesh(jointGeometry, createJointMaterial(color));
        scene.add(mesh);
        return mesh;
    });

    const boneConnections = [
        [0, 1], [0, 2], [1, 3], [2, 4], [3, 4], [3, 5], [4, 6],
        [5, 7], [6, 8], [3, 9], [4, 10], [9, 10], [9, 11],
        [11, 13], [10, 12], [12, 14]
    ];

    const lines = boneConnections.map(([startIdx, endIdx]) => {
        const geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
        const material = new THREE.LineBasicMaterial({ color: jointColors[startIdx] });
        const line = new THREE.Line(geometry, material);
        scene.add(line);
        return line;
    });

    // 바닥 및 조명 설정
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(10, 10), new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide }));
    floor.rotation.x = Math.PI / 2;
    floor.position.y = 0;
    scene.add(floor);

    const gridHelper = new THREE.GridHelper(10, 10, 0x888888, 0xcccccc);
    gridHelper.position.y = 0.01;  // floor 보다는 약간 높게
    scene.add(gridHelper);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 2);
    directionalLight.position.set(0, 6, 0);
    scene.add(directionalLight);
    scene.add(new THREE.AmbientLight(0xffffff, 1));

    // GLTFLoader를 사용하여 외부 glb 파일 모델 로드
    const loader = new THREE.GLTFLoader();
    const loadModel = (filename, x, y, z) => {
        loader.load(`model/${filename}`, (gltf) => {
            const model = gltf.scene;
            model.position.set(x, y, z);
            scene.add(model);
        }, undefined, (error) => {
            console.error(`An error occurred while loading the model '${filename}':`, error);
        });
    };
    loadModel('Obstacles.glb', 0, 0, 0);    // 물건
    //loadModel('Wall.glb', 0.6, 0, 0);   // 벽

    // 넘어짐 감지 메시지 설정
    const fallMessage = document.createElement('div');
    Object.assign(fallMessage.style, {
        position: 'absolute',
        top: `${canvas.offsetTop}px`,
        left: `${canvas.offsetLeft}px`,
        color: 'red',
        fontSize: '16px',
        fontWeight: 'bold',
        display: 'none'
    });
    fallMessage.innerText = 'Fall-Down Detected';
    document.body.appendChild(fallMessage);

    // 윈도우 리사이즈 이벤트 처리
    window.addEventListener('resize', () => {
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);

        fallMessage.style.top = `${canvas.offsetTop}px`;
        fallMessage.style.left = `${canvas.offsetLeft}px`;
    });

    const updateJoints = (jointData) => {
        jointData.forEach((joint, i) => {
            jointMeshes[i].position.set(-joint.x, joint.y, joint.z);
        });

        lines.forEach((line, i) => {
            const [p1, p2] = boneConnections[i].map(idx => jointMeshes[idx].position);
            line.geometry.attributes.position.array.set([p1.x, p1.y, p1.z, p2.x, p2.y, p2.z]);
            line.geometry.attributes.position.needsUpdate = true;
        });
    };

    // Web Worker로부터 메시지 수신
    socketWorker.onmessage = (event) => {
        latestMessage = event.data; // 최신 메시지로 교체
    };

    socketWorker.postMessage({ command: "start", url: `ws://${ip}:${port}` });

    const processLatestMessage = () => {
        if (latestMessage) {
            const { jointData, rmse, captureTime, eventName } = latestMessage;
            updateJoints(jointData);

            // Delay (captureTime과 현재 시간과의 차이) 계산
            const [datePart, timePart] = captureTime.split('_'); // 날짜와 시간을 구분
            const [hours, minutes, seconds] = timePart.split('-'); // 시간을 세부적으로 나눔
            const [sec, millis] = seconds.split('.'); // 초와 밀리초 나눔

            // 날짜와 시간 정보를 명확하게 설정하여 Date 객체로 변환
            const captureTimeDate = new Date(`${datePart}T${hours}:${minutes}:${sec}.${millis}`);

            let timeDifferenceSeconds = 0; // 기본값으로 설정

            if (!isNaN(captureTimeDate.getTime())) { // Date 변환이 유효한지 체크
                const currentTime = new Date(); // 현재 시간
                const timeDifference = currentTime - captureTimeDate; // 밀리초 단위 차이
                timeDifferenceSeconds = timeDifference / 1000; // 초 단위로 변환
                //console.log(`Delay: ${timeDifferenceSeconds.toFixed(3)} seconds`);
            } else {
                console.log('Invalid captureTime format.');
            }

            // fallMessage에 검은색과 빨간색 부분을 분리하여 표시
            fallMessage.style.display = 'block';
            fallMessage.innerHTML = `
                <span style="color: black;">
                    RMSE: ${(rmse * 100).toFixed(1)} cm / Delay: ${timeDifferenceSeconds.toFixed(3)} s
                </span>
                ${eventName !== 'None' ? `<span style="color: red;"> / Event: ${eventName}</span>` : ""}
            `;

            console.log(`CaptureTime: ${captureTime}`);
            latestMessage = null; // 처리 후 초기화
        }
        requestAnimationFrame(processLatestMessage);
    };

    processLatestMessage(); // 시작

    const animate = () => {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    };
    animate();


    // Function to close the WebSocket connection via Worker
    window.CloseWebGLSocket = () => {
        if (socketWorker) {
            socketWorker.postMessage({ command: "stop" });
            console.log("WebSocket connection closed via button click");
        } else {
            console.log("WebSocket Worker not running or already stopped");
        }
    };
};
