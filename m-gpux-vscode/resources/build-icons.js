// Render icon.svg → icon.png (128×128, the VS Code marketplace size).
// Run with: node resources/build-icons.js
const sharp = require("sharp");
const path = require("path");

const SRC = path.join(__dirname, "icon.svg");
const OUT = path.join(__dirname, "icon.png");

sharp(SRC, { density: 384 })
  .resize(128, 128)
  .png({ compressionLevel: 9 })
  .toFile(OUT)
  .then(() => console.log(`Wrote ${OUT}`))
  .catch((err) => { console.error(err); process.exit(1); });
