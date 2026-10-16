# ============================================================================
# Unreal text file decoding
# ============================================================================


def read_unreal_text_file(filename):
    """
    Read an Unreal-generated text export with encoding detection.

    Unreal text exporters may emit:
        UTF-8
        UTF-8 with BOM
        UTF-16 LE
        UTF-16 BE

    UTF-16 is particularly important because Unreal may choose it when the
    exported UObject contains Unicode text.

    Returns:
        (text, encoding)
    """

    with open(
        filename,
        "rb"
    ) as file:

        raw = file.read()

    if not raw:
        return "", "empty"

    # ------------------------------------------------------------------------
    # Explicit BOMs
    # ------------------------------------------------------------------------

    if raw.startswith(
        b"\xff\xfe"
    ):
        return (
            raw.decode(
                "utf-16"
            ),
            "utf-16-le"
        )

    if raw.startswith(
        b"\xfe\xff"
    ):
        return (
            raw.decode(
                "utf-16"
            ),
            "utf-16-be"
        )

    if raw.startswith(
        b"\xef\xbb\xbf"
    ):
        return (
            raw.decode(
                "utf-8-sig"
            ),
            "utf-8-sig"
        )

    # ------------------------------------------------------------------------
    # Normal UTF-8
    # ------------------------------------------------------------------------

    try:

        return (
            raw.decode(
                "utf-8"
            ),
            "utf-8"
        )

    except UnicodeDecodeError:
        pass

    # ------------------------------------------------------------------------
    # UTF-16 without BOM
    #
    # Unreal usually writes a BOM, but handle the no-BOM case defensively.
    # ASCII-heavy UTF-16 looks like:
    #
    # LE: B\0e\0g\0i\0n\0
    # BE: \0B\0e\0g\0i\0n
    # ------------------------------------------------------------------------

    sample = raw[
        :min(
            len(raw),
            4096
        )
    ]

    nul_count = sample.count(
        b"\x00"
    )

    if (
        sample
        and nul_count > len(sample) * 0.20
    ):

        even_nuls = sum(
            1
            for index in range(
                0,
                len(sample),
                2
            )
            if sample[index] == 0
        )

        odd_nuls = sum(
            1
            for index in range(
                1,
                len(sample),
                2
            )
            if sample[index] == 0
        )

        encoding = (
            "utf-16-le"
            if odd_nuls > even_nuls
            else "utf-16-be"
        )

        return (
            raw.decode(
                encoding,
                errors="replace"
            ),
            encoding
        )

    # ------------------------------------------------------------------------
    # Last resort
    #
    # Some legacy Unreal text can still contain ANSI characters.
    # Keep the export readable instead of failing the entire source pass.
    # ------------------------------------------------------------------------

    return (
        raw.decode(
            "cp1252",
            errors="replace"
        ),
        "cp1252"
    )