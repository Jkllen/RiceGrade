// Minimal ambient declaration for the Cloudflare Workers TCP sockets runtime.
declare module 'cloudflare:sockets' {
  interface WorkersSocket {
    readonly readable: ReadableStream<Uint8Array>;
    readonly writable: WritableStream<Uint8Array>;
    close():void;
  }
  export function connect(
    address:{hostname:string;port:number},
    options?:{secureTransport?:'off'|'on'|'starttls';allowHalfOpen?:boolean}
  ):WorkersSocket;
}
