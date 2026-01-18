const socket = io();
socket.emit("join", { room: "genel" });

socket.on("message", data => {
    const chat = document.getElementById("chat");
    const div = document.createElement("div");

    div.className = "message " + (data.user === myUsername ? "me" : "other");
    div.innerHTML = `<b>${data.user}</b><br>${data.msg}`;

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
});

function sendMessage() {
    const input = document.getElementById("msg");
    if (input.value.trim() === "") return;

    socket.emit("message", {
        room: "genel",
        msg: input.value
    });
    input.value = "";
}
