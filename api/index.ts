import { NestFactory } from '@nestjs/core';
import { ExpressAdapter } from '@nestjs/platform-express';
import { AppModule } from '../src/module';
import express from 'express';
import 'reflect-metadata';
const server = express();
let ready: Promise<any>;
export default async function handler(req:any,res:any){
  if(!ready) ready=(async()=>{const app=await NestFactory.create(AppModule,new ExpressAdapter(server),{logger:false});await app.init();return app;})();
  await ready; server(req,res);
}
