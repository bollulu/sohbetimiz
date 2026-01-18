const socket = io();
const chatId = window.location.pathname.split("/")[2];

if (chatId) socket.emit("join", { chat_id: chatId });

function send() {
    const msg = document.getElementById("msg").value;
    socket.emit("send_message", { chat_id: chatId, text: msg });
    document.getElementById("msg").value = "";
}

socket.on("receive_message", data => {
    const div = document.createElement("div");
    div.innerText = data.sender + ": " + data.text;
    document.getElementById("messages").appendChild(div);
});
