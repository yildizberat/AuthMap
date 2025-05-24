const express = require("express");
const app = express();

// Rol kontrol middleware'i
function checkRole(role) {
  return function (req, res, next) {
    req.user = { role }; // örnek rol
    next();
  };
}

app.get("/admin", checkRole("admin"), (req, res) => {
  res.send("Admin panel");
});

app.post("/admin/delete", checkRole("admin"), (req, res) => {
  res.send("Admin silme işlemi");
});

app.get("/profile", checkRole("user"), (req, res) => {
  res.send("Kullanıcı profili");
});

app.listen(3000, () => console.log("Server çalışıyor..."));