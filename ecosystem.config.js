module.exports = {
  apps: [
    {
      name: 'bot-keo-nhom-5d-nepnon',
      script: 'bot.py',
      interpreter: './venv/bin/python',
      cwd: __dirname,
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: '1',
      },
    },
  ],
};
