let socketWorker = new Worker("/js/messageWorker.js");
let latestMessage = null; // �ֽ� �޽��� ���� ����

window.GetPose3D = (canvasId, ip, port) => {
    console.log(`[HHCHOI] Connect request to ${ip} on port ${port}!!`);

    // �⺻ ����
    const canvas = document.getElementById(canvasId);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
    camera.position.set(0, 5, 5);

    const renderer = new THREE.WebGLRenderer({ canvas });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.setClearColor(0xd3d3d3, 1);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.update();

    // ���� ����
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

    // �ٴ� �� ���� ����
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(10, 10), new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide }));
    floor.rotation.x = Math.PI / 2;
    floor.position.y = 0;
    scene.add(floor);

    const gridHelper = new THREE.GridHelper(10, 10, 0x888888, 0xcccccc);
    gridHelper.position.y = 0.01;  // floor ���ٴ� �ణ ����
    scene.add(gridHelper);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 2);
    directionalLight.position.set(0, 6, 0);
    scene.add(directionalLight);
    scene.add(new THREE.AmbientLight(0xffffff, 1));

    // GLTFLoader�� ����Ͽ� �ܺ� glb ���� �� �ε�
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
    loadModel('Obstacles.glb', 0, 0, 0);    // ����
    //loadModel('Wall.glb', 0.6, 0, 0);   // ��

    // �Ѿ��� ���� �޽��� ����
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

    // ������ �������� �̺�Ʈ ó��
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

    // Web Worker�κ��� �޽��� ����
    socketWorker.onmessage = (event) => {
        latestMessage = event.data; // �ֽ� �޽����� ��ü
    };

    socketWorker.postMessage({ command: "start", url: `ws://${ip}:${port}` });

    const processLatestMessage = () => {
        if (latestMessage) {
            const { jointData, rmse, captureTime, eventName } = latestMessage;
            updateJoints(jointData);

            // Delay (captureTime�� ���� �ð����� ����) ���
            const [datePart, timePart] = captureTime.split('_'); // ��¥�� �ð��� ����
            const [hours, minutes, seconds] = timePart.split('-'); // �ð��� ���������� ����
            const [sec, millis] = seconds.split('.'); // �ʿ� �и��� ����

            // ��¥�� �ð� ������ ��Ȯ�ϰ� �����Ͽ� Date ��ü�� ��ȯ
            const captureTimeDate = new Date(`${datePart}T${hours}:${minutes}:${sec}.${millis}`);

            let timeDifferenceSeconds = 0; // �⺻������ ����

            if (!isNaN(captureTimeDate.getTime())) { // Date ��ȯ�� ��ȿ���� üũ
                const currentTime = new Date(); // ���� �ð�
                const timeDifference = currentTime - captureTimeDate; // �и��� ���� ����
                timeDifferenceSeconds = timeDifference / 1000; // �� ������ ��ȯ
                //console.log(`Delay: ${timeDifferenceSeconds.toFixed(3)} seconds`);
            } else {
                console.log('Invalid captureTime format.');
            }

            // fallMessage�� �������� ������ �κ��� �и��Ͽ� ǥ��
            fallMessage.style.display = 'block';
            fallMessage.innerHTML = `
                <span style="color: black;">
                    RMSE: ${(rmse * 100).toFixed(1)} cm / Delay: ${timeDifferenceSeconds.toFixed(3)} s
                </span>
                ${eventName !== 'None' ? `<span style="color: red;"> / Event: ${eventName}</span>` : ""}
            `;

            console.log(`CaptureTime: ${captureTime}`);
            latestMessage = null; // ó�� �� �ʱ�ȭ
        }
        requestAnimationFrame(processLatestMessage);
    };

    processLatestMessage(); // ����

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
