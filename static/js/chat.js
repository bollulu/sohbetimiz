const socket = io();

function send() {
  const msg = document.getElementById("msg").value;
  socket.emit("send_message", {
    username: USERNAME,
    message: msg
  });
  document.getElementById("msg").value = "";
}

socket.on("receive_message", data => {
  const p = document.createElement("p");
  p.innerHTML = `<b>${data.username}:</b> ${data.message}`;
  document.getElementById("chat").appendChild(p);
});
