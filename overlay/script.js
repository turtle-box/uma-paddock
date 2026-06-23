window.addEventListener('onEventReceived', function (obj) {
    if (!obj.detail.event) {
      return;
    }
});

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
    setGates(1, fieldData.trainer1gates);
    setGates(2, fieldData.trainer2gates);
    setGates(3, fieldData.trainer3gates);
    setIcons(fieldData, baseUrl);
});
