const { exec } = require("child_process");

exports.run = (value) => exec(`echo ${value}`);
