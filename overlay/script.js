window.addEventListener('onEventReceived', function (obj) {
    if (!obj.detail.event) {
      return;
    }
});

const FALLBACK_STACK = "Montserrat, sans-serif";

function applyFontStack(family) {
    if (family) {
        $("#widget").css("font-family", `'${family}', ${FALLBACK_STACK}`);
    } else {
        $("#widget").css("font-family", FALLBACK_STACK);
    }
}

async function loadCustomFont(fontFamily, fontUrl) {
    const family = (fontFamily || "").trim();
    const url = (fontUrl || "").trim();

    if (!family) {
        applyFontStack("");
        return;
    }

    if (url) {
        try {
            const face = new FontFace(family, `url(${url})`);
            await face.load();
            document.fonts.add(face);
            applyFontStack(family);
            return;
        } catch (err) {
            console.warn("Custom font URL failed to load:", err);
        }
    }

    applyFontStack(family);
}

function setGates(trainerIndex, gatesRaw) {
    const gates = gatesRaw.split(",").map(s => s.trim());
    for (let i = 0; i < 3; i++) {
        const uma = $(`#tr${trainerIndex}uma${i + 1}`);
        uma.removeClass(function (_, cls) {
            return (cls.match(/\bgate\d+\b/g) || []).join(" ");
        });
        uma.addClass(`gate${gates[i]}`);
        uma.find(".uma-gate").text(gates[i] || "");
    }
}

function setIcons(fieldData, baseUrl) {
    for (let t = 1; t <= 3; t++) {
        for (let u = 1; u <= 3; u++) {
            const slug = fieldData[`tr${t}uma${u}`];
            const img = $(`#tr${t}uma${u}`).find(".uma-icon");
            img.attr("src", slug ? `${baseUrl}/${slug}.png` : "");
        }
    }
}

window.addEventListener('onWidgetLoad', function (obj) {
    const fieldData = obj.detail.fieldData;
    const baseUrl = (fieldData.iconBaseUrl || "").replace(/\/$/, "");
    $.when(loadCustomFont(fieldData.customFont, fieldData.fontUrl)).fail(console.warn);
    setGates(1, fieldData.trainer1gates);
    setGates(2, fieldData.trainer2gates);
    setGates(3, fieldData.trainer3gates);
    setIcons(fieldData, baseUrl);
});
