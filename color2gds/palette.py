"""Render saved candidate spectra without running the optical solver."""
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .layout import read_gds
from .optics import color


def _load_palette(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    with np.load(directory / 'palette.npz') as data:
        wavelengths = data['wavelength_nm']
        spectra = np.vstack([data['reflectance'], data['blank']])
    count = len(spectra) - 1
    round_no = manifest['optimization_history'][-1]['round']
    geometries, indices, _ = read_gds(
        directory / f'calibration_{round_no}.gds', {**manifest, 'grid': [count, 1]})
    geometries = [geometries[int(i)] for i in indices[0]]
    return manifest, wavelengths, spectra, geometries


def palette_data(directory):
    """Return saved, unpolarized spectra in the same candidate order as the PNG."""
    manifest, wavelengths, spectra, geometries = _load_palette(directory)
    entries = []
    for i, spectrum in enumerate(spectra):
        c = color(spectrum, wavelengths)
        rgb = np.uint8(np.array(c['rgb']) * 255 + .5)
        g = geometries[i] if i < len(geometries) else None
        entries.append({
            'label': f'Candidate {i+1:02}' if g is not None else 'No pattern (substrate)',
            'hex': '#' + ''.join(f'{v:02x}' for v in rgb),
            'out_of_srgb': bool(c['out_of_srgb']),
            'pitch_nm': float(g['pitch'] * 1000) if g is not None else None,
            'width_nm': float(g['width'] * 1000) if g is not None else None,
            'reflectance': spectrum.tolist(),
        })
    return {'wavelength_nm': wavelengths.tolist(), 'entries': entries,
            'blank_comparison_only': manifest.get('opaque_pixels_allow_blank') is False}


TEXT = {
    'en': {'summary': '{count} computed candidates + unpatterned substrate color',
           'conditions': 'D65, unpolarized / incidence {theta:g}° / {modes} modes / {step:g} nm step',
           'scope': 'Swatches correspond to the stack and dimensions of this result.',
           'candidate': 'Candidate {n:02}', 'blank': 'No pattern (substrate)',
           'geometry': 'Period {pitch:g} / width {width:g} nm',
           'blank_only': 'Comparison only, not drawn', 'blank_stack': 'Stack without patterned films',
           'gamut': ' * outside sRGB',
           'footer': 'Predicted from saved spectra. Lists the searched candidates; not the full gamut and not measured.'},
    'ja': {'summary': '計算済み候補 {count}色 ＋ パターンなしの下地色',
           'conditions': 'D65・非偏光 / 入射角 {theta:g}° / {modes}次数 / 波長刻み {step:g} nm',
           'scope': '色見本はこの結果の積層・寸法条件に対応します。',
           'candidate': '候補 {n:02}', 'blank': 'パターンなし（下地）',
           'geometry': '周期 {pitch:g} / 線幅 {width:g} nm',
           'blank_only': '比較用・描画には不使用', 'blank_stack': 'パターン膜を除いた積層',
           'gamut': ' ※sRGB範囲外',
           'footer': '保存済みスペクトルによる予測色。探索した候補の一覧であり、全色域の網羅・実測値ではありません。'},
}


def palette_png(directory, lang='en'):
    text = TEXT[lang]
    manifest, wavelengths, spectra, geometries = _load_palette(directory)
    count = len(geometries)
    font_path = Path(__file__).resolve().parents[1] / 'webgui/static/fonts/NotoSansJP.ttf'
    font = ImageFont.truetype(str(font_path), 18)
    small = ImageFont.truetype(str(font_path), 15)
    title = ImageFont.truetype(str(font_path), 24)
    columns, card_width, card_height = 5, 244, 170
    width = 40 + columns * card_width
    height = 170 + ((len(spectra) + columns - 1) // columns) * card_height + 60
    image = Image.new('RGB', (width, height), '#f5f6f8')
    draw = ImageDraw.Draw(image)
    name = manifest['stack']['name'].replace('₂', '2')
    while draw.textlength(name, font=title) > width - 40:
        name = name[:-2] + '…'
    draw.text((20, 18), name, font=title, fill='#202830')
    draw.text((20, 62), text['summary'].format(count=count), font=font, fill='#202830')
    settings = manifest['settings']
    draw.text((20, 96), text['conditions'].format(theta=settings['theta'], modes=settings['modes'], step=settings['step_nm']), font=small, fill='#505b66')
    draw.text((20, 122), text['scope'], font=small, fill='#505b66')
    for i, spectrum in enumerate(spectra):
        x, y = 20 + (i % columns) * card_width, 165 + (i // columns) * card_height
        c = color(spectrum, wavelengths)
        rgb = tuple(np.uint8(np.array(c['rgb']) * 255 + .5))
        hex_color = '#' + ''.join(f'{v:02x}' for v in rgb)
        draw.rectangle((x, y, x + card_width - 16, y + 85), fill=rgb)
        label = text['candidate'].format(n=i + 1) if i < count else text['blank']
        draw.text((x, y + 92), label, font=font, fill='#202830')
        if i < count:
            g = geometries[i]
            detail = text['geometry'].format(pitch=g['pitch'] * 1000, width=g['width'] * 1000)
        else:
            detail = (text['blank_only'] if manifest.get('opaque_pixels_allow_blank') is False
                      else text['blank_stack'])
        draw.text((x, y + 122), detail, font=small, fill='#505b66')
        draw.text((x, y + 144), hex_color + (text['gamut'] if c['out_of_srgb'] else ''), font=small, fill='#505b66')
    draw.text((20, height - 45), text['footer'], font=small, fill='#505b66')
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()
