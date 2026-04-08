# reports/tag_generator.py
#
# Tag Generation Service
#
# Generates properly instrumented GPT (Google Publisher Tag) ad tags and
# passback/fallback tags with hnt_* key-values for unified attribution.
# All generated tags inject:
#   hnt_pub_id, hnt_prop_id, hnt_plc_id, hnt_source, hnt_site, hnt_env
#
# Supports:
#   - Standard GPT tags (for publisher site integration)
#   - Passback / GAM 360 fallback tags (for third-party demand passback)
#   - Ad unit path convention enforcement

import logging
from textwrap import dedent

logger = logging.getLogger(__name__)

GPT_LIBRARY_URL = 'https://securepubads.g.doubleclick.net/tag/js/gpt.js'


def generate_ad_unit_path(network_code, publisher_id, property_id, placement_name):
    """
    Build a structured GAM ad unit path.
    Convention: /{network_code}/hnt/pub_{publisher_id}/{property_id}/{placement_name}
    If property_id doesn't start with prop_, it's prefixed automatically.
    """
    safe_placement = (placement_name or 'default').strip().lower().replace(' ', '_')
    prop_segment = str(property_id)
    if not prop_segment.startswith('prop_'):
        prop_segment = f"prop_{prop_segment}"
    return f"/{network_code}/hnt/pub_{publisher_id}/{prop_segment}/{safe_placement}"


def generate_gpt_tag(
    network_code,
    publisher_id,
    property_id,
    placement_id,
    placement_name,
    ad_size,
    source_type='mcm_direct',
    env='web',
    custom_ad_unit_path=None,
    div_id=None,
    lazy_load=True,
    collapse_empty=True,
):
    """
    Generate a complete GPT ad tag snippet with hnt_* key-values.

    Returns a dict with:
      - head_js: JS to include in <head>
      - body_html: HTML + JS to place in the page body
      - ad_unit_path: the resolved ad unit path
      - targeting: dict of key-values being set
    """
    ad_unit_path = custom_ad_unit_path or generate_ad_unit_path(
        network_code, publisher_id, property_id, placement_name
    )

    if not div_id:
        safe_name = (placement_name or 'ad').strip().lower().replace(' ', '-').replace('_', '-')
        div_id = f"hnt-ad-{safe_name}"

    sizes = _parse_ad_sizes(ad_size)
    size_js = _sizes_to_js(sizes)

    targeting = {
        'hnt_pub_id': str(publisher_id),
        'hnt_prop_id': str(property_id),
        'hnt_plc_id': str(placement_id),
        'hnt_source': source_type,
        'hnt_env': env,
    }

    targeting_js = '\n      '.join(
        f".setTargeting('{k}', '{v}')"
        for k, v in targeting.items()
    )

    # hnt_site is set dynamically from window.location.hostname
    targeting_js += "\n      .setTargeting('hnt_site', window.location.hostname)"

    head_js = dedent(f"""\
    <script async src="{GPT_LIBRARY_URL}"></script>
    <script>
      window.googletag = window.googletag || {{queue: []}};
      googletag.cmd.push(function() {{
        var slot = googletag.defineSlot('{ad_unit_path}', {size_js}, '{div_id}')
          {targeting_js}
          .addService(googletag.pubads());
        {"googletag.pubads().collapseEmptyDivs();" if collapse_empty else ""}
        {"googletag.pubads().enableLazyLoad({fetchMarginPercent: 200, renderMarginPercent: 100, mobileScaling: 2.0});" if lazy_load else ""}
        googletag.enableServices();
      }});
    </script>""")

    body_html = dedent(f"""\
    <div id="{div_id}" style="min-width:{sizes[0][0] if sizes else 300}px; min-height:{sizes[0][1] if sizes else 250}px;">
      <script>
        googletag.cmd.push(function() {{ googletag.display('{div_id}'); }});
      </script>
    </div>""")

    return {
        'head_js': head_js,
        'body_html': body_html,
        'ad_unit_path': ad_unit_path,
        'targeting': targeting,
        'div_id': div_id,
    }


def generate_passback_tag(
    network_code,
    publisher_id,
    property_id,
    placement_id,
    placement_name,
    ad_size,
    source_type='gam360_passback',
    env='web',
    custom_ad_unit_path=None,
):
    """
    Generate a passback / fallback tag for GAM 360 demand.

    Passback tags are self-contained: they include the GPT library load,
    slot definition, and key-values — designed to be pasted into a third-party
    ad server's passback creative.

    The key difference from a standard tag: hnt_source defaults to
    'gam360_passback' and the tag is designed to work inside iframes /
    SafeFrame without relying on parent page context.
    """
    ad_unit_path = custom_ad_unit_path or generate_ad_unit_path(
        network_code, publisher_id, property_id, placement_name
    )

    sizes = _parse_ad_sizes(ad_size)
    size_js = _sizes_to_js(sizes)

    targeting = {
        'hnt_pub_id': str(publisher_id),
        'hnt_prop_id': str(property_id),
        'hnt_plc_id': str(placement_id),
        'hnt_source': source_type,
        'hnt_env': env,
    }

    targeting_js = '\n        '.join(
        f".setTargeting('{k}', '{v}')"
        for k, v in targeting.items()
    )

    # For passback tags, try to detect the actual site but fall back gracefully
    site_detection = dedent("""\
        var hntSite = 'unknown';
        try {
          hntSite = window.top.location.hostname || window.location.hostname;
        } catch(e) {
          try { hntSite = document.referrer ? new URL(document.referrer).hostname : window.location.hostname; }
          catch(e2) { hntSite = window.location.hostname; }
        }""")

    div_id = f"hnt-pb-{placement_id.replace('_', '-') if placement_id else 'fallback'}"

    tag = dedent(f"""\
    <!-- HNT Passback Tag: {placement_name} ({ad_size}) -->
    <div id="{div_id}">
    <script>
      (function() {{
        {site_detection}

        var gptLoaded = typeof googletag !== 'undefined' && googletag.apiReady;
        if (!gptLoaded) {{
          var s = document.createElement('script');
          s.src = '{GPT_LIBRARY_URL}';
          s.async = true;
          document.head.appendChild(s);
        }}

        window.googletag = window.googletag || {{queue: []}};
        googletag.cmd.push(function() {{
          var slot = googletag.defineSlot('{ad_unit_path}', {size_js}, '{div_id}')
            {targeting_js}
            .setTargeting('hnt_site', hntSite)
            .addService(googletag.pubads());
          googletag.pubads().collapseEmptyDivs();
          googletag.enableServices();
          googletag.display('{div_id}');
        }});
      }})();
    </script>
    </div>
    <!-- End HNT Passback Tag -->""")

    return {
        'tag': tag,
        'ad_unit_path': ad_unit_path,
        'targeting': targeting,
        'div_id': div_id,
    }


def generate_multi_slot_page(slots, network_code, publisher_id, property_id, env='web'):
    """
    Generate a multi-slot page setup with a single GPT library load and
    multiple slot definitions — more efficient than individual tags.

    Parameters
    ----------
    slots : list of dict
        Each dict: {placement_id, placement_name, ad_size, source_type?, div_id?}

    Returns a dict with head_js and list of body_snippets.
    """
    slot_definitions = []
    body_snippets = []

    for i, slot in enumerate(slots):
        plc_id = slot['placement_id']
        plc_name = slot['placement_name']
        ad_size = slot['ad_size']
        src = slot.get('source_type', 'mcm_direct')
        div_id = slot.get('div_id') or f"hnt-ad-{i}-{plc_name.lower().replace(' ', '-')}"

        ad_unit_path = generate_ad_unit_path(
            network_code, publisher_id, property_id, plc_name
        )
        sizes = _parse_ad_sizes(ad_size)
        size_js = _sizes_to_js(sizes)

        targeting = {
            'hnt_pub_id': str(publisher_id),
            'hnt_prop_id': str(property_id),
            'hnt_plc_id': str(plc_id),
            'hnt_source': src,
            'hnt_env': env,
        }
        targeting_js = ''.join(
            f".setTargeting('{k}', '{v}')" for k, v in targeting.items()
        )
        targeting_js += ".setTargeting('hnt_site', window.location.hostname)"

        slot_definitions.append(
            f"    googletag.defineSlot('{ad_unit_path}', {size_js}, '{div_id}'){targeting_js}.addService(googletag.pubads());"
        )

        w = sizes[0][0] if sizes else 300
        h = sizes[0][1] if sizes else 250
        body_snippets.append({
            'div_id': div_id,
            'html': f'<div id="{div_id}" style="min-width:{w}px;min-height:{h}px;"><script>googletag.cmd.push(function(){{ googletag.display(\'{div_id}\'); }});</script></div>',
            'placement_id': plc_id,
        })

    slot_defs = '\n'.join(slot_definitions)
    head_js = dedent(f"""\
    <script async src="{GPT_LIBRARY_URL}"></script>
    <script>
      window.googletag = window.googletag || {{queue: []}};
      googletag.cmd.push(function() {{
    {slot_defs}
        googletag.pubads().collapseEmptyDivs();
        googletag.pubads().enableLazyLoad({{fetchMarginPercent: 200, renderMarginPercent: 100, mobileScaling: 2.0}});
        googletag.enableServices();
      }});
    </script>""")

    return {
        'head_js': head_js,
        'body_snippets': body_snippets,
    }


def _parse_ad_sizes(size_str):
    """Parse size string like '300x250' or '300x250,728x90' into list of [w,h]."""
    if not size_str:
        return [[300, 250]]
    sizes = []
    for part in str(size_str).split(','):
        part = part.strip().lower()
        if 'x' in part:
            try:
                w, h = part.split('x', 1)
                sizes.append([int(w.strip()), int(h.strip())])
            except (ValueError, TypeError):
                continue
        elif part == 'responsive' or part == 'fluid':
            sizes.append('fluid')
    return sizes or [[300, 250]]


def _sizes_to_js(sizes):
    """Convert parsed sizes to JS array literal."""
    if len(sizes) == 1:
        s = sizes[0]
        if s == 'fluid':
            return "'fluid'"
        return f"[{s[0]}, {s[1]}]"
    parts = []
    for s in sizes:
        if s == 'fluid':
            parts.append("'fluid'")
        else:
            parts.append(f"[{s[0]}, {s[1]}]")
    return f"[{', '.join(parts)}]"
