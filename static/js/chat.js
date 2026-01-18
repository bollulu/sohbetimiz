const socket = io();
const room = "genel";

socket.emit("join", { room: room });

socket.on("message", data => {
    const chat = document.getElementById("chat");

    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message");

    if (data.user === myUsername) {
        msgDiv.classList.add("me");
    } else {
        msgDiv.classList.add("other");
    }

    msgDiv.innerHTML = `<b>${data.user}</b><br>${data.msg}`;
    chat.appendChild(msgDiv);
    chat.scrollTop = chat.scrollHeight;
});

function sendMessage() {
    const input = document.getElementById("msg");
    if (input.value.trim() === "") return;

    socket.emit("message", {
        room: room,
        msg: input.value
    });

    input.value = "";
}

/* ENTER ile gönder */
document.getElementById("msg").addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
        sendMessage();
    }
});
