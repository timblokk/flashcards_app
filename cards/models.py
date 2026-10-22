from os import times
from time import time
from django.conf import settings
from django.db import models
from itertools import chain
import datetime
from django.core.exceptions import ValidationError
# Create your models here.
NUM_BOXES = 6
BOXES = range(1, NUM_BOXES + 1)
CAT_CHOICES = [
    ('Arabic', 'Arabic'),
    ('Test_Card','test cards'),
    ('livres', 'Livres/Journaux'),
    ('VHS_B1/B2', 'VHS_B1/B2'),
    ('F5','Francais 5'),
    ('F6','Francais 6'),
    ('F7','Francais 7'),
]

LANG_CHOICES = [
    ('de', 'Allemand'),
    ('en', 'Anglais'),
    ('pl', 'polognais'),
    ('it', 'italien'),
    ('pt', 'portogaise'),
    ('es', 'espagnol'),
]


class AccountCategorySettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="category_settings",
        on_delete=models.CASCADE,
    )
    arabic_only = models.BooleanField(default=True)


class Card(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="cards",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    answer =  models.CharField(max_length = 300)
    answer_vocalized = models.TextField(blank=True)
    question_en = models.CharField(max_length = 100)
    question_es = models.CharField(max_length = 100)
    question_de = models.CharField(max_length = 100)
    question_it = models.CharField(max_length = 100)
    question_pt = models.CharField(max_length = 100)
    question_pl = models.CharField(max_length = 100)

    box = models.IntegerField(
        choices=zip(BOXES, BOXES),
        default=BOXES[0],
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_moved = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=9, choices= CAT_CHOICES,    default='F6')
    language = models.CharField(max_length=15, choices = LANG_CHOICES, default ="de" )

    def __str__(self):
        return self.question


    def move(self, solved):
        new_box = self.box + 1 if solved else BOXES[0]
        if new_box in BOXES:
            self.box = new_box
            self.date_moved = datetime.datetime.now(datetime.timezone.utc)
            self.save()
        return self

    @property
    def to_repeat(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        min_age = {
        1:1,
        2:2,
        3:4,
        4:7,
        5:14,
        6:30
        }
        to_repeat = (now - self.date_moved- datetime.timedelta(days=min_age[self.box])).total_seconds() > 0
        return to_repeat

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "answer", "question_de"],
                name="uniq_card_user_answer_de",
                condition=~models.Q(question_de=""),
            ),
            models.UniqueConstraint(
                fields=["user", "answer", "question_en"],
                name="uniq_card_user_answer_en",
                condition=~models.Q(question_en=""),
            ),
            models.UniqueConstraint(
                fields=["user", "answer", "question_pl"],
                name="uniq_card_user_answer_pl",
                condition=~models.Q(question_pl=""),
            ),
            models.UniqueConstraint(
                fields=["user", "answer", "question_it"],
                name="uniq_card_user_answer_it",
                condition=~models.Q(question_it=""),
            ),
            models.UniqueConstraint(
                fields=["user", "answer", "question_pt"],
                name="uniq_card_user_answer_pt",
                condition=~models.Q(question_pt=""),
            ),
            models.UniqueConstraint(
                fields=["user", "answer", "question_es"],
                name="uniq_card_user_answer_es",
                condition=~models.Q(question_es=""),
            ),
        ]


class DictionaryEntry(models.Model):
    language_pair = models.CharField(max_length=16, default="en-ar")
    headword = models.CharField(max_length=255)
    search_key = models.CharField(max_length=255, blank=True, default="", db_collation="nocase")
    translation = models.TextField()
    vocalized_translation = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["language_pair", "search_key"], name="dict_pair_search_idx"),
        ]

    def __str__(self):
        return self.headword

    def save(self, *args, **kwargs):
        if not self.search_key:
            self.search_key = self.headword.casefold()
        super().save(*args, **kwargs)