module.exports = {
  apps: [
    {
      name: "tele_bot",
      script: "env/bin/python",
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8002"
    }
  ]
};
