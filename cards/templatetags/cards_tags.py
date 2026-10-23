from django import template
from cards.models import BOXES, Card

register = template.Library()

@register.inclusion_tag("cards/box_links.html", takes_context=True)
def boxes_as_links(context):
    boxes = []
    for box_num in BOXES:
        card_count = Card.objects.filter(
            user=context["request"].user,
            box=box_num,
        ).count()
        boxes.append({
            "number": box_num,
            "card_count": card_count,
        })
    return {"boxes": boxes}

@register.inclusion_tag("cards/repeat_link.html", takes_context=True)
def repeat_box_as_link(context):
    repeat_count=0
    for card in Card.objects.filter(
        user=context["request"].user,
    ):
        if(card.to_repeat):
            repeat_count = repeat_count +1

    return {"repeat_count":repeat_count}