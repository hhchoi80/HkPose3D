let sockets = {};  // �� WebSocket�� �����ϴ� ��ü

window.GetStream = (canvasId, ip, port) => {
    console.log(`[HHCHOI] Connect request to ${ip} on port ${port}!!`);

    // �⺻ ����
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');

    // WebSocket ���� ���� �Լ�
    const openSocket = () => {
        const socket = new WebSocket(`ws://${ip}:${port}`);       // 127.0.0.1 or 192.168.1.75

        socket.onopen = function () {
            console.log(`Connected to WebSocket server ${ip} on port ${port}`);
        };

        socket.onmessage = function (event) {
            // �̹��� ������ ����
            const arrayBuffer = event.data;

            // Blob���� ��ȯ�Ͽ� �̹����� ó��
            const blob = new Blob([arrayBuffer], { type: 'image/jpeg' });
            const url = URL.createObjectURL(blob);
            const img = new Image();

            img.onload = function () {
                // Canvas�� �̹��� ǥ��
                canvas.width = img.width;
                canvas.height = img.height;
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);  // ��� �� URL ����

                // Blob ũ�� (����Ʈ ����)
                const blobSize = blob.size;
                console.log(`Image data received (${blobSize} bytes)`);

                // Canvas ���� Blob ũ��� ī�޶� ���� ������ ���� ū �۾��� ǥ��
                ctx.font = '90px Arial';  // �۾� ũ�� ����
                ctx.fillStyle = 'black';

                // ������ ���� ��ġ��Ű�� (�ؽ�Ʈ �ʺ� ���� ��ġ ����)
                const text = `Rx Data: ${blobSize} bytes`;
                const textWidth = ctx.measureText(text).width;
                ctx.fillText(text, canvas.width - textWidth - 10, 90);  // �����ʿ��� 10px ����
            };
            img.src = url;
        };

        socket.onclose = function () {
            console.log(`WebSocket connection closed on port ${port}`);
        };

        socket.onerror = function (error) {
            console.log('WebSocket error:', error);
        };

        sockets[canvasId] = socket;  // �ش� WebSocket�� ����
    };

    openSocket();

    // WebSocket ���� ���� �Լ�
    window.closeSockets = () => {
        Object.keys(sockets).forEach((key) => {
            if (sockets[key]) {
                sockets[key].close();
                console.log(`Closed WebSocket for ${key}`);
                sockets[key] = null;
            }
        });
    };

    // WebSocket �ٽ� �����ϴ� �Լ�
    window.reopenSockets = () => {
        if (!sockets[canvasId]) {
            openSocket();
        }
    };
};
