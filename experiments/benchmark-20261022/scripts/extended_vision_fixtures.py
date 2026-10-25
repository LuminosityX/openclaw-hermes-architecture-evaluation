from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,random,hashlib
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'fixtures/extended-vision';folder.mkdir(exist_ok=True)
rng=random.Random(20261022);cases=[]
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
for i in range(10):
    image=Image.new('RGB',(640,440),'white');draw=ImageDraw.Draw(image)
    code=''.join(rng.choice('ABCDEFGHJKMNPQRSTUVWXYZ23456789') for _ in range(6));total=rng.randrange(100,9999);count=2+i%6
    draw.text((25,25),'CODE: '+code,font=font,fill='black');draw.text((25,85),f'TOTAL: {total}',font=font,fill='black')
    for j in range(count):
        x=35+(j%4)*145;y=180+(j//4)*115;draw.ellipse((x,y,x+64,y+64),fill='#1261d8')
    draw.rectangle((500,320,560,380),fill='#d82424')
    path=folder/f'card-{i:02d}.png';image.save(path)
    cases.append({'case_id':f'vision-{i:02d}','path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'expected':{'code':code,'blue_circles':count,'total':total}})
(ROOT/'results/extended-vision-cases.json').write_text(json.dumps({'cases':cases,'prompt':'Read the attached image. Return only a JSON object with keys code (string after CODE), blue_circles (number of blue circles), total (integer after TOTAL). Ignore the red square.'},indent=2))
print('Prepared10imagecases')
