traffic_light = {
    run: function(interval, subdir, root_element){
        $.ajax(subdir, {
                dataType: "json",
                timeout: 250,
                success: function(data){
                            console.log("hallo");
                            traffic_light.got_answer(root_element, data);
                           }
            });
        window.setTimeout(function(){traffic_light.run(interval, subdir, root_element);}, interval );
    },
    got_answer:function(root_element, data){
        console.log(data);
    }
}

$("document").ready(function()
{
    traffic_light.run(250, "/interface/state");
});