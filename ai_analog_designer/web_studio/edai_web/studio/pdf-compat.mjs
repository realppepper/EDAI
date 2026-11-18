// PDF.js uses Uint8Array.toHex for document fingerprints.
// Keep text extraction usable in engines where that method is not yet present.
if (!Uint8Array.prototype.toHex) {
 Object.defineProperty(Uint8Array.prototype,'toHex',{
  configurable:true,writable:true,
  value:function(){return Array.from(this,v=>v.toString(16).padStart(2,'0')).join('');}
 });
}
