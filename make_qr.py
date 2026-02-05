import qrcode

BASE_URL = "http://192.168.1.50:5000"  # change to your laptop IP

pcs = [
  ("L1","TOKEN1"),
  ("L2","TOKEN2"),
]

for pc_id, token in pcs:
    url = f"{BASE_URL}/pc/{pc_id}?token={token}"
    img = qrcode.make(url)
    img.save(f"qr_{pc_id}.png")
