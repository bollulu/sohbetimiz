<div id="story-bar">
    <div class="add-story" onclick="document.getElementById('st-file').click()">
        <div class="s-circle">+</div>
        <small>Hikaye Ekle</small>
    </div>
    <div id="story-list" style="display:flex; gap:15px;">
        {% for owner, items in stories.items() %}
        <div class="story-user" onclick='openStoryPlayer({{ items | tojson }}, "{{ owner }}")'>
            <img src="{{ items[0].content if items[0].type == 'image' else '/static/video_icon.png' }}" class="s-circle-active">
            <small>{{ owner }}</small>
        </div>
        {% endfor %}
    </div>
</div>

<div id="story-player" class="story-modal">
    <div class="story-header">
        <b id="st-owner"></b>
        <button onclick="closeStory()" style="color:white; background:none; border:none; font-size:20px;">✕</button>
    </div>
    <div id="st-content-area" onclick="nextStory()">
        </div>
    <div class="story-footer">
        <p id="st-music-info"></p>
        <button id="st-delete-btn" onclick="deleteCurrentStory()" style="display:none; background:red; color:white;">Hikayemi Sil</button>
    </div>
</div>

<script>
    let currentStoryIndex = 0;
    let currentStoryList = [];
    let currentStoryOwner = "";

    function openStoryPlayer(list, owner) {
        currentStoryList = list;
        currentStoryOwner = owner;
        currentStoryIndex = 0;
        document.getElementById('story-player').style.display = 'flex';
        showStory();
    }

    function showStory() {
        const item = currentStoryList[currentStoryIndex];
        const area = document.getElementById('st-content-area');
        const musicInfo = document.getElementById('st-music-info');
        const delBtn = document.getElementById('st-delete-btn');
        
        document.getElementById('st-owner').innerText = currentStoryOwner;
        delBtn.style.display = (currentStoryOwner === me) ? "block" : "none";
        musicInfo.innerText = item.music ? "🎵 " + item.music : "";

        if(item.type === 'image') {
            area.innerHTML = `<img src="${item.content}" class="st-media">`;
        } else {
            area.innerHTML = `<video src="${item.content}" autoplay class="st-media"></video>`;
        }
    }

    function nextStory() {
        currentStoryIndex++;
        if(currentStoryIndex < currentStoryList.length) {
            showStory();
        } else {
            closeStory();
        }
    }

    function deleteCurrentStory() {
        const item = currentStoryList[currentStoryIndex];
        socket.emit('delete_story', {id: item.id});
        closeStory();
    }

    function closeStory() {
        document.getElementById('story-player').style.display = 'none';
        document.getElementById('st-content-area').innerHTML = "";
    }

    // --- AVATAR GÜNCELLEME ---
    function updateMyAvatar(input) {
        const reader = new FileReader();
        reader.onload = e => {
            const base64 = e.target.result;
            socket.emit('update_avatar', {avatar: base64});
        };
        reader.readAsDataURL(input.files[0]);
    }

    socket.on('avatar_changed', data => {
        // Sayfadaki tüm ilgili avatarları anında güncelle
        document.querySelectorAll(`.ava-${data.username}`).forEach(img => img.src = data.avatar);
        if(data.username === me) alert("Profil resminiz güncellendi!");
    });

    // --- GÖRÜNTÜLÜ ARAMA ---
    async function startCall() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({video: true, audio: true});
            document.getElementById('v-modal').style.display = 'block';
            document.getElementById('loc-v').srcObject = stream;
            // Arama isteği gönder
            socket.emit('call_request', {to: currentRoom});
        } catch (err) {
            alert("Kameraya erişilemedi!");
        }
    }

    socket.on('refresh_stories', () => {
        location.reload(); // Hikayeler değişince listeyi güncelle
    });
</script>
