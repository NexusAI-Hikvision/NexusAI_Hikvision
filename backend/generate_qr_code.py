import qrcode

def build_qr(url: str, save_path: str):
    """Generates a QR code PNG for the given URL and saves it to save_path."""
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(save_path)
    return img