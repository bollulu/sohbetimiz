const socket = io();

socket.emit("join", { room: currentRoom });

socket.on("message", data => {
    const div = document.createElement("div");
    div.className = "message " + (data.user === myUsername ? "me" : "other");
    div.innerHTML = `<b>${data.user}</b><br>${data.msg}`;
    document.getElementById("chat").appendChild(div);
});

function sendMessage() {
    const input = document.getElementById("msg");
    if (!input.value.trim()) return;
    socket.emit("message", { room: currentRoom, msg: input.value });
    input.value = "";
}
