import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_wdx9ijs1uncp12_5ae6/temp/drag/Cloudra_省自科(2).pptx'));
console.log('Slides methods',Object.getOwnPropertyNames(Object.getPrototypeOf(p.slides)));
const s=p.slides.items[2];console.log('shapes',Object.getOwnPropertyNames(Object.getPrototypeOf(s.shapes)));
const sh=p.resolve('sh/n6ls3alk');console.log('text',Object.getOwnPropertyNames(Object.getPrototypeOf(sh.text)));console.log('text style',JSON.stringify(sh.text.style));
sh.text.typeface='Hiragino Sans GB';sh.text.color='#155C44';
await (await PresentationFile.exportPptx(p)).save('.deck-work/roundtrip.pptx');
