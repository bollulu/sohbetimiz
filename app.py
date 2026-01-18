<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Giriş</title>
    <style>
        body {
            font-family: Arial;
            background: #111;
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
        }
        form {
            background: #222;
            padding: 30px;
            border-radius: 10px;
        }
        input, button {
            padding: 10px;
            margin-top: 10px;
            width: 100%;
        }
        button {
            background: #25D366;
            border: none;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <form method="POST">
        <h2>Kullanıcı Adı</h2>
        <input type="text" name="username" required>
        <button type="submit">Giriş Yap</button>
    </form>
</body>
</html>
