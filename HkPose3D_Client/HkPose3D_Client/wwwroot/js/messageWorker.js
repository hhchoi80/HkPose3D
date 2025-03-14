let socket;

self.onmessage = (event) => {
    const { command, url } = event.data;

    if (command === "start") {
        socket = new WebSocket(url);

        socket.onmessage = (e) => {
            try {
                console.log("Message received!");
                const data = JSON.parse(e.data);
                self.postMessage({
                    jointData: data["3D_points"],
                    rmse: data["rmse"],
                    captureTime: data["capture_time"],
                    eventName: data["event_name"] || ""  // event_name이 없으면 빈 문자열
                });
            } catch (error) {
                console.error("Worker: Invalid JSON received", error.message);
            }
        };

        socket.onerror = (e) => console.error("Worker: WebSocket Error", e);
        socket.onclose = () => console.log("Worker: WebSocket closed.");
    }


    // 추가된 stop 명령
    if (command === "stop" && socket) {
        socket.close();
        console.log("Worker: WebSocket connection closed.");
    }
};
