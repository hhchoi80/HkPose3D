let sockets = {};  // 각 WebSocket을 저장하는 객체

window.GetStream = (canvasId, ip, port) => {
    console.log(`[HHCHOI] Connect request to ${ip} on port ${port}!!`);

    // 기본 설정
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');

    // WebSocket 연결 설정 함수
    const openSocket = () => {
        const socket = new WebSocket(`ws://${ip}:${port}`);       // 127.0.0.1 or 192.168.1.75

        socket.onopen = function () {
            console.log(`Connected to WebSocket server ${ip} on port ${port}`);
        };

        socket.onmessage = function (event) {
            // 이미지 데이터 수신
            const arrayBuffer = event.data;

            // Blob으로 변환하여 이미지로 처리
            const blob = new Blob([arrayBuffer], { type: 'image/jpeg' });
            const url = URL.createObjectURL(blob);
            const img = new Image();

            img.onload = function () {
                // Canvas에 이미지 표시
                canvas.width = img.width;
                canvas.height = img.height;
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);  // 사용 후 URL 해제

                // Blob 크기 (바이트 단위)
                const blobSize = blob.size;
                console.log(`Image data received (${blobSize} bytes)`);

                // Canvas 위에 Blob 크기와 카메라 라벨을 오른쪽 위에 큰 글씨로 표시
                ctx.font = '90px Arial';  // 글씨 크기 설정
                ctx.fillStyle = 'black';

                // 오른쪽 위에 위치시키기 (텍스트 너비를 구해 위치 조정)
                const text = `Rx Data: ${blobSize} bytes`;
                const textWidth = ctx.measureText(text).width;
                ctx.fillText(text, canvas.width - textWidth - 10, 90);  // 오른쪽에서 10px 안쪽
            };
            img.src = url;
        };

        socket.onclose = function () {
            console.log(`WebSocket connection closed on port ${port}`);
        };

        socket.onerror = function (error) {
            console.log('WebSocket error:', error);
        };

        sockets[canvasId] = socket;  // 해당 WebSocket을 저장
    };

    openSocket();

    // WebSocket 연결 끊기 함수
    window.closeSockets = () => {
        Object.keys(sockets).forEach((key) => {
            if (sockets[key]) {
                sockets[key].close();
                console.log(`Closed WebSocket for ${key}`);
                sockets[key] = null;
            }
        });
    };

    // WebSocket 다시 연결하는 함수
    window.reopenSockets = () => {
        if (!sockets[canvasId]) {
            openSocket();
        }
    };
};
