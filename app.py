<!DOCTYPE html>
<html>
<head>
    <title>Sohbetimiz</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        :root { --wp-green: #25D366; --wp-dark: #075e54; }
        body { margin:0; display:flex; height:100vh; font-family:sans-serif; overflow:hidden; }
        #side { width:300px; background:white; border-right:1px solid #ddd; display:flex; flex-direction:column; }
        #main { flex:1; display:flex; flex-direction:column; background:#e5ddd5; position:relative; }
        #story-bar { height:100px; background:white; display:flex; align-items:center; padding:0 15px; gap:15px; border-bottom:1px solid #ddd; overflow-x:auto; z-index:10; }
        .st-ring { width:60px; height:60px; border-radius:50%; border:3px solid var(--wp-green); padding:2px; cursor:pointer; object-fit:cover; }
        #chat-box { flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:10px; z-index:5; }
        .msg { display:flex; align-items:flex-end; gap:8px; max-width:70%; }
        .msg.me { align-self:flex-end; flex-direction:row-reverse; }
        .bubble { background:white; padding:10px; border-radius:12px; position:relative; box-shadow:0 1px 1px rgba(0,0,0,0.1); }
        .me .bubble { background:#dcf8c6; }
        #st-viewer { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:black; z-index:2000; align-items:center; justify-content:center; }
        #st-viewer img, #st-viewer video { max-width:90%; max-height:80vh; }
        .cam-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); z-index:3000; flex-direction:column; align-items:center; justify-content:center; }
    </style>
</head>
<body>

<div id="st-viewer">
    <div id="st-media-box"></div>
    <button onclick="closeSt()" style="position:absolute; top:20px; right:20px; color:white; font-size:30px; background:none; border:none; cursor:pointer;">×</button>
</div>

<div id="cam-overlay" class="cam-overlay">
    <video id="cam-video" autoplay style="width:80%; max-width:500px; border-radius:10px;"></video>
    <div style="margin-top:20px;">
        <button onclick="takeSnap()" style="padding:10px 20px; border-radius:50px; border:none; cursor:pointer;">📸 Çek</button>
        <button onclick="closeCam()" style="padding:10px 20px; background:red; color:white; border-radius:50px; border:none; cursor:pointer;">İptal</button>
    </div>
</div>

<div id="side">
    <div style="padding:15px; background:#ededed; font-weight:bold; display:flex; justify-content:space-between;">
        <span>Aktifler</span>
        <button onclick="location.href='/logout'">🚪</button>
    </div>
    <div id="online-list"></div>
</div>

<div id="main">
    <div id="story-bar">
        <div onclick="openSource()" style="text-align:center; cursor:pointer;">
            <div style="width:60px;height:60px;border-radius:50%;background:#eee;display:flex;align-items:center;justify-content:center;font-size:30px;">+</div>
            <small>Ekle</small>
        </div>
        <div id="st-list" style="display:flex; gap:15px;"></div>
    </div>
    <div id="chat-box">
        {% for m in initial_msgs %}
        <div class="msg {{ 'me' if m.username == user.username else '' }}" id="m-{{m.id}}">
            <img src="{{ m.user_avatar }}" class="user-ava-img-{{m.username}}" style="width:30px;height:30px;border-radius:50%;object-fit:cover">
            <div class="bubble"><b>{{ m.username }}</b><br>{{ m.content }}</div>
        </div>
        {% endfor %}
    </div>
    <div style="padding:10px; background:#f0f0f0; display:flex; gap:10px;">
        <input type="text" id="mIn" style="flex:1; padding:10px; border-radius:20px; border:none;" onkeypress="if(event.key==='Enter') send()">
        <button onclick="send()">🚀</button>
    </div>
</div>

<input type="file" id="st-file" style="display:none" onchange="uploadStory(this)">

<script>
    const socket = io();
    const myName = "{{ user.username }}";
    let storyData = {};

    function send() {
        const i = document.getElementById('mIn');
        if(i.value.trim()) { socket.emit('message', {content: i.value}); i.value=''; }
    }

    socket.on('new_message', d => {
        const isMe = d.user === myName;
        document.getElementById('chat-box').insertAdjacentHTML('beforeend', `
            <div class="msg ${isMe?'me':''}">
                <img src="${d.avatar}" class="user-ava-img-${d.user}" style="width:30px;height:30px;border-radius:50%;object-fit:cover">
                <div class="bubble"><b>${d.user}</b><br>${d.content}</div>
            </div>
        `);
        document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
    });

    socket.on('user_status', users => {
        let h = "";
        for(let u in users) h += `<div style="padding:10px; border-bottom:1px solid #eee;">${u} ${u===myName?'<b>(Siz)</b>':''}</div>`;
        document.getElementById('online-list').innerHTML = h;
    });

    // Hikaye Kaynak Seçimi
    function openSource() {
        if(confirm("Kamerayı kullanmak için TAMAM, Dosya seçmek için İPTAL.")) openCam();
        else document.getElementById('st-file').click();
    }

    // Kamera
    async function openCam() {
        document.getElementById('cam-overlay').style.display='flex';
        const s = await navigator.mediaDevices.getUserMedia({video:true});
        document.getElementById('cam-video').srcObject = s;
    }
    function closeCam() {
        document.getElementById('cam-video').srcObject.getTracks().forEach(t=>t.stop());
        document.getElementById('cam-overlay').style.display='none';
    }
    function takeSnap() {
        const v = document.getElementById('cam-video');
        const c = document.createElement('canvas');
        c.width=v.videoWidth; c.height=v.videoHeight;
        c.getContext('2d').drawImage(v,0,0);
        socket.emit('add_story', {content: c.toDataURL('image/jpeg'), type:'image'});
        closeCam();
    }

    function uploadStory(i) {
        const r = new FileReader();
        r.onload = e => socket.emit('add_story', {content: e.target.result, type: i.files[0].type.split('/')[0]});
        r.readAsDataURL(i.files[0]);
    }

    socket.on('all_stories', d => {
        storyData = d;
        let h = "";
        for(let u in d) h += `<div onclick="viewSt('${u}')"><img src="${d[u].avatar}" class="st-ring"><br><small>${u}</small></div>`;
        document.getElementById('st-list').innerHTML = h;
    });

    function viewSt(u) {
        const item = storyData[u].items[0];
        const box = document.getElementById('st-media-box');
        document.getElementById('st-viewer').style.display='flex';
        box.innerHTML = item.type === 'video' ? `<video src="${item.content}" autoplay></video>` : `<img src="${item.content}">`;
        setTimeout(closeSt, 5000);
    }
    function closeSt() { document.getElementById('st-viewer').style.display='none'; }
</script>
</body>
</html>
