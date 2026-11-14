import { Module } from '@nestjs/common';
import { Controller, Get, Post, Req, Res, Injectable } from '@nestjs/common';
import { Request, Response } from 'express';
import { MongoClient, Collection } from 'mongodb';
import { readFileSync } from 'fs';
import { join } from 'path';
import { randomBytes, timingSafeEqual } from 'crypto';

const EMERGENCY = /胸痛|心绞痛|胸口.{0,4}(闷|疼|痛|压)|呼吸困难|喘不上气|喘不过气|气短|憋气|意识不清|昏迷|晕倒|昏厥|不省人事|叫不醒|大出血|吐.{0,3}血|咯血|便血.{0,3}(多|大量)|突发.{0,6}(剧烈|炸裂|要炸).{0,4}头痛|半边(身体|身子|脸|胳膊|腿).{0,4}(无力|麻木|动不了)|口角歪斜|言语不清|严重过敏|喉头水肿|过敏性休克/;
const CRISIS = /自杀|不想活|想死|结束生命|活着(没|无)意思|轻生|自残|割腕|割手|跳楼|上吊/;
const EMERGENCY_CARD = '⚠️ **紧急提醒**：你描述的情况可能是需要立即就医的急症。\n\n请**马上拨打 120（急救）**，或让身边人送你去最近的急诊，**不要自行驾车**。\n\n等待期间：保持冷静；如果患者意识不清，让其**侧卧**、保持呼吸道通畅；不要给昏迷者喂水喂药。\n\n——如果你只是想了解相关知识、并不是现在正在发生，请告诉我，我会正常回答你。';
const CRISIS_CARD = '🆘 如果你此刻有伤害自己的念头或计划，请**立即联系你信任的人**，或拨打全国心理援助热线 **12356**（24 小时）；情况紧急请拨打 **120** 或前往最近医院急诊。\n\n你不需要一个人扛，现在找人陪着你是最重要的事。';
const DEFAULTS = { base_url:'https://api.deepseek.com', model_fast:'deepseek-flash', model_deep:'deepseek-v4-pro', temperature:1 };

@Injectable()
class Store {
  private clientPromise?: Promise<MongoClient>;
  private collectionPromise?: Promise<Collection>;
  private collection() {
    if (!process.env.MONGODB_URI) throw new Error('缺少 MONGODB_URI 环境变量，请在 Vercel 项目设置中配置 MongoDB Atlas 连接串。');
    if (!this.clientPromise) this.clientPromise = new MongoClient(process.env.MONGODB_URI, { maxPoolSize: 5, serverSelectionTimeoutMS: 10000 }).connect();
    if (!this.collectionPromise) this.collectionPromise = this.clientPromise.then(client => client.db(process.env.MONGODB_DATABASE || 'zhiheng').collection('app_state'));
    return this.collectionPromise;
  }
  async get(k:string, fallback:any={}) { const col=await this.collection(); const row=await col.findOne({_id:'zh:'+k} as any); return row ? row.value : fallback; }
  async set(k:string,v:any) { const col=await this.collection(); await col.updateOne({_id:'zh:'+k} as any,{$set:{value:v,updatedAt:new Date()}},{upsert:true}); }
}

@Controller()
class Api {
  constructor(private store:Store) {}
  private async config(){ return {...DEFAULTS,...await this.store.get('config',{})}; }
  private async auth(req:Request,res:Response){ const cfg=await this.config(); if(!cfg.access_password) return true; const token=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('hz_auth='))?.slice(8); if(token===cfg.auth_token) return true; if(req.path==='/') return false; res.status(401).json({ok:false,error:'未登录'}); return false; }
  @Get('/') async root(@Req() req:Request,@Res() res:Response){if(!await this.auth(req,res))return res.status(200).send('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>知衡 · 访问验证</title><style>body{font:16px sans-serif;background:linear-gradient(160deg,#0f766e,#134e4a);min-height:100vh;display:grid;place-items:center}.card{background:white;padding:32px;border-radius:16px;text-align:center}input,button{padding:12px;border-radius:8px;border:1px solid #cbd5e1}button{background:#0f766e;color:white}</style><form class="card"><h1>知衡 · 访问验证</h1><p>请输入访问密码</p><input id="p" type="password" inputmode="numeric" required><p><button>进入</button></p><div id="e"></div></form><script>document.querySelector("form").onsubmit=async e=>{e.preventDefault();let r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:document.querySelector("#p").value})});if(r.ok)location.reload();else document.querySelector("#e").textContent="密码错误"}</script>');return res.sendFile(join(process.cwd(),'public','index.html')); }
  @Get('/api/config') async getConfig(@Req() req:Request,@Res() res:Response){ if(!await this.auth(req,res))return; const c=await this.config(); return res.json({api_key_set:!!c.api_key,api_key_tail:(c.api_key||'').slice(-4),base_url:c.base_url,model_fast:c.model_fast,model_deep:c.model_deep,temperature:c.temperature,access_password_set:!!c.access_password}); }
  @Post('/api/login') async login(@Req() req:Request,@Res() res:Response){ const c=await this.config(); if(req.body.password && req.body.password===c.access_password){ const token=randomBytes(32).toString('hex'); c.auth_token=token; await this.store.set('config',c); res.cookie('hz_auth',token,{httpOnly:true,sameSite:'lax',maxAge:2592000000,secure:process.env.NODE_ENV==='production'}); return res.json({ok:true}); } return res.status(401).json({ok:false,error:'密码错误'}); }
  @Get('/api/profile') async profile(@Req() q:Request,@Res() r:Response){if(!await this.auth(q,r))return; return r.json({profile:await this.store.get('profile')});}
  @Post('/api/profile') async saveProfile(@Req() q:Request,@Res() r:Response){if(!await this.auth(q,r))return; await this.store.set('profile',q.body.profile||{});return r.json({ok:true});}
  @Get('/api/sexual') async sexual(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;return r.json({profile:await this.store.get('sexual')});}
  @Post('/api/sexual') async saveSexual(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;await this.store.set('sexual',q.body.profile||{});return r.json({ok:true});}
  @Get('/api/messages') async messages(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;return r.json({messages:await this.store.get('messages',[])});}
  @Post('/api/clear') async clear(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;await this.store.set('messages',[]);return r.json({ok:true});}
  @Post('/api/config') async saveConfig(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;const c=await this.config(); if(q.body.api_key)c.api_key=q.body.api_key.trim(); if(q.body.clear_api_key)c.api_key=''; for(const k of ['base_url','model_fast','model_deep','access_password'])if(q.body[k])c[k]=q.body[k].trim(); if(q.body.temperature!=null)c.temperature=Number(q.body.temperature); await this.store.set('config',c);return r.json({ok:true});}
  @Get('/api/image') async image(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;return r.json({images:await this.store.get('images',[]),recent:await this.store.get('recent',[]),auto_refine:await this.store.get('auto_refine',true),counter:await this.store.get('counter',0),threshold:5});}
  @Post('/api/image') async imagePost(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;let a=await this.store.get('images',[]);const b=q.body; if(b.action==='delete')a=a.filter(x=>x.id!==b.id); else if(b.action==='update')a=a.map(x=>x.id===b.id?{...x,content:b.content,domain:b.domain,updated_at:Date.now()/1000|0}:x); else {if(!b.content)return r.status(400).json({ok:false,error:'内容为空'});const id=Date.now();a.unshift({id,content:b.content,domain:b.domain||'其他',source:'手动添加',created_at:id,updated_at:id});await this.store.set('images',a);return r.json({ok:true,id});}await this.store.set('images',a);return r.json({ok:true});}
  @Post('/api/recent') async recent(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;await this.store.set('recent',(await this.store.get('recent',[])).filter(x=>x.id!==q.body.id));return r.json({ok:true});}
  @Post('/api/refine_config') async refineConfig(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;if(q.body.auto_refine!==undefined)await this.store.set('auto_refine',!!q.body.auto_refine);return r.json({ok:true,auto_refine:await this.store.get('auto_refine',true)});}
  @Post('/api/refine') async refine(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;return r.json({ok:true,skipped:true,counter:await this.store.get('counter',0)});}
  @Post('/api/chat') async chat(@Req()q:Request,@Res()r:Response){
    if(!await this.auth(q,r))return;
    const text=String(q.body.message||'').trim(), images=Array.isArray(q.body.images)?q.body.images.slice(0,4):[];
    if(!text&&!images.length)return r.status(400).json({ok:false,error:'消息为空'});
    const history=await this.store.get('messages',[]); let answer='';
    if(CRISIS.test(text)) answer=CRISIS_CARD; else if(EMERGENCY.test(text)) answer=EMERGENCY_CARD;
    else {
      const c=await this.config(); if(!c.api_key) answer='还没有配置 API Key。请先点击右上角「设置」，填入你的 DeepSeek API Key 再对话。';
      else try {
        const prompt=readFileSync(join(process.cwd(),'01-人设与系统提示词.md'),'utf8');
        const mark='▽▽▽ 提示词正文开始', end='▽▽▽ 提示词正文结束'; let system=prompt; const i=prompt.indexOf(mark); if(i>=0){const s=prompt.indexOf('\n',i)+1,e=prompt.indexOf(end,s);system=prompt.slice(s,e<0?undefined:e).trim();}
        system+='\n\n【用户健康档案】\n'+JSON.stringify(await this.store.get('profile',{}));
        const msgs=[{role:'system',content:system},...history.slice(-30).map(x=>({role:x.role,content:x.content})),{role:'user',content:text||'请看看我发的图片。'}];
        const model=q.body.mode==='deep'&&!images.length?c.model_deep:c.model_fast;
        const upstream=await fetch(c.base_url.replace(/\/$/,'')+'/chat/completions',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+c.api_key},body:JSON.stringify({model,messages:msgs,stream:false,temperature:c.temperature})});
        if(!upstream.ok) throw new Error('模型服务返回错误（HTTP '+upstream.status+'）。'); const data:any=await upstream.json(); answer=data.choices?.[0]?.message?.content||'（没有收到回复）';
      } catch(e:any){answer='连接模型服务失败：'+(e?.message||e);}
    }
    for(const url of images){const m=String(url).match(/^data:(image\/[\w.+-]+);base64,(.+)$/s);if(m){const id=randomBytes(12).toString('hex'); await this.store.set('img:'+id,{type:m[1],data:m[2]});}}
    history.push({role:'user',content:text,images:[]},{role:'assistant',content:answer,images:[]}); await this.store.set('messages',history.slice(-200));
    r.setHeader('Content-Type','text/event-stream; charset=utf-8');r.setHeader('Cache-Control','no-cache');r.setHeader('Connection','keep-alive');r.write('data: '+JSON.stringify({role:'assistant',delta:answer,safety:CRISIS.test(text)||EMERGENCY.test(text)})+'\n\n');r.end('data: {"done":true}\n\n');
  }
  @Get('/api/images/:id') async getImage(@Req()q:Request,@Res()r:Response){if(!await this.auth(q,r))return;const v=await this.store.get('img:'+q.params.id,null);if(!v)return r.sendStatus(404);r.type(v.type).send(Buffer.from(v.data,'base64'));}
}

@Module({controllers:[Api],providers:[Store]}) export class AppModule {}
