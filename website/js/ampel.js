traffic_light = function (name, root_element) {
        let me = this;
        this.error_count = 0;
        this.name = name;
        this.root_element = root_element;
        this.group_key = "";
        this.loaded = false;
        this.set_way=function(value){
                        $.ajax("/api/v1/command", {
                                data : JSON.stringify({"give_way": !!value}),
                            contentType : 'application/json',
                            type : 'POST',
                        });
                };
        this.error=function(textStatus){
                me.error_count++;
                if (me.error_count>4){
                        me.red_circle.hide();
                        me.yellow_circle.hide();
                        me.green_circle.hide();
                }
        };
        this.update=function(data){
                if (! me.loaded) return;
                me.error_count = 0;
                if (!data.alive) {
                        $(".inop", me.root_element).show();
                } else {
                        $(".inop", me.root_element).hide();
                        $(".battvoltage", me.root_element).val(data.batt_voltage/100.0);
                        if (data.lamp_currents[0]>10) me.red_circle.show(); else me.red_circle.hide();
                        if (data.lamp_currents[1]>10) me.yellow_circle.show(); else me.yellow_circle.hide();
                        if (data.lamp_currents[2]>10) me.green_circle.show(); else me.green_circle.hide();
                }

        };
        $.ajax("/image/ampel.svg",
                {
                dataType:"text",
                success:function(data){
                        $(".tlpicture", me.root_element).replaceWith(data);
                        me.red_circle = $(".red", me.root_element);
                        me.yellow_circle = $(".yellow", me.root_element);
                        me.green_circle = $(".green", me.root_element);
                        me.error_count = 0;
                        me.loaded = true;
                        me.root_element.show();
                }
        });
        $(".setred").click( function(){
                me.set_way(0);
        });
        $(".setgreen").click( function(){
                me.set_way(1);
        });
}

let traffic_lights={};

$("document").ready(function() {
        setInterval( () => {
                $.ajax("/api/v1/states",
                        {
                        dataType:"json",
                        success:function(data){
                            let original = $(".traffic_light_area.template");
                            let skel = original.clone();
                            skel.removeClass("template");
                            original.hide();
                            let section = $("#uebersicht");
                            for (var name in data){
                                if (!(name in traffic_lights)) {
                                        let local_copy = skel.clone();
                                        $(".name", local_copy).text(name);
                                        local_copy.attr("id", name);
                                        traffic_lights[name] = new traffic_light(name, local_copy);
                                        section.append(local_copy);
                                }
                                traffic_lights[name].update(data[name]);
                            }
                        },
                });
        }, 1000);
});

