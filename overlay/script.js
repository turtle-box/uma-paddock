window.addEventListener('onEventReceived', function (obj) {
    if (!obj.detail.event) {
      return;
    }
});

var FALLBACK_STACK = "Montserrat, sans-serif";
var GATE_CLASSES = "gate1 gate2 gate3 gate4 gate5 gate6 gate7 gate8 gate9";

function applyFontStack(family) {
    if (family) {
        $("#widget").css("font-family", "'" + family + "', " + FALLBACK_STACK);
    } else {
        $("#widget").css("font-family", FALLBACK_STACK);
    }
}

function loadCustomFont(fontFamily, fontUrl) {
    var family = (fontFamily || "").trim();
    var url = (fontUrl || "").trim();

    if (!family) {
        applyFontStack("");
        return;
    }

    if (url) {
        var face = new FontFace(family, "url(" + url + ")");
        face.load().then(function () {
            document.fonts.add(face);
            applyFontStack(family);
        }).catch(function (err) {
            console.warn("Custom font URL failed to load:", err);
            applyFontStack(family);
        });
        return;
    }

    applyFontStack(family);
}

function setGates(trainerIndex, gatesRaw) {
    var gates = gatesRaw.split(",").map(function (s) { return s.trim(); });
    var i;
    for (i = 0; i < 3; i++) {
        var uma = $("#tr" + trainerIndex + "uma" + (i + 1));
        uma.removeClass(GATE_CLASSES);
        uma.addClass("gate" + gates[i]);
        uma.find(".uma-gate").text(gates[i] || "");
    }
}

function setIcons(fieldData, baseUrl) {
    var t, u, slug, img;
    for (t = 1; t <= 3; t++) {
        for (u = 1; u <= 3; u++) {
            slug = fieldData["tr" + t + "uma" + u];
            img = $("#tr" + t + "uma" + u).find(".uma-icon");
            img.attr("src", slug ? baseUrl + "/" + slug + ".png" : "");
        }
    }
}

window.addEventListener('onWidgetLoad', function (obj) {
    var fieldData = obj.detail.fieldData;
    var baseUrl = (fieldData.iconBaseUrl || "").replace(/\/$/, "");
    loadCustomFont(fieldData.customFont, fieldData.fontUrl);
    setGates(1, fieldData.trainer1gates);
    setGates(2, fieldData.trainer2gates);
    setGates(3, fieldData.trainer3gates);
    setIcons(fieldData, baseUrl);
});
