const socket = io();
const chatId = window.location.pathname.split("/").pop();

socket.emit("join", { chat_id: chatId });

function send() {
    const text = document.getElementById("msg").value;
    socket.emit("send_message", { chat_id: chatId, text: text });
}

socket.on("receive_message", data => {
    const div = document.createElement("div");
    div.innerText = data.sender + ": " + data.text;
    document.getElementById("messages").appendChild(div);
});
