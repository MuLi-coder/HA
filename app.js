// Vercel's NestJS entrypoint. Keep the direct @nestjs/core import here so
// framework detection can identify the application before invocation.
const { NestFactory } = require('@nestjs/core');
const { ExpressAdapter } = require('@nestjs/platform-express');
const express = require('express');
const path = require('path');
require('reflect-metadata');

const server = express();
server.use(express.static(path.join(process.cwd(), 'public')));
let appPromise;

module.exports = async (req, res) => {
  if (!appPromise) {
    appPromise = (async () => {
      const { AppModule } = require('./dist/module');
      const app = await NestFactory.create(AppModule, new ExpressAdapter(server), { logger: false });
      await app.init();
      return app;
    })();
  }
  await appPromise;
  server(req, res);
};
