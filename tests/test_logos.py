import struct

from pipeline.logos import file_name, logo_for, png_size


def make_png(w, h):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00"


def test_png_size():
    assert png_size(make_png(128, 128)) == (128, 128)
    assert png_size(b"not an image") is None


def test_exact_name_match_only(tmp_path):
    (tmp_path / file_name("stripe.com")).write_bytes(make_png(128, 128))
    (tmp_path / file_name("honeywell.com")).write_bytes(make_png(128, 128))
    assert logo_for("Stripe", tmp_path) == "assets/logos/stripe.com.png"
    assert logo_for("STRIPE Inc.", tmp_path) == "assets/logos/stripe.com.png"        # case/suffix ignored
    assert logo_for("Honeywell Technologies", tmp_path) == "assets/logos/honeywell.com.png"  # listed alias
    assert logo_for("Stripe Consulting Services", tmp_path) is None              # not the same company
    assert logo_for("Some Small Startup", tmp_path) is None


def test_no_file_means_no_logo(tmp_path):
    assert logo_for("Stripe", tmp_path) is None   # listed, but logo not downloaded -> initials
