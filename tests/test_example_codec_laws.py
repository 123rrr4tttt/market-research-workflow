from hypothesis import strategies as st

from functorial_kit import KitExample, Nested, codec_laws, kit_example_codec

SAFE = 2**53 - 1
examples = st.builds(
    KitExample,
    id=st.text(),
    tags=st.lists(st.text()).map(tuple),
    count=st.integers(min_value=-SAFE, max_value=SAFE),
    nested=st.builds(Nested, flag=st.booleans(), note=st.none() | st.text()),
)

TestKitExampleCodec = codec_laws(kit_example_codec, examples)
