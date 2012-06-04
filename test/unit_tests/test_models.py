from nose.tools import raises, assert_equals, nottest
import os, unittest, json, time, datetime
from test.mocks import MockDao
from copy import deepcopy

from totalimpact import models, default_settings
from totalimpact.providers import provider
from totalimpact import dao, app

COLLECTION_DATA = {
    "id": "uuid-goes-here",
    "collection_name": "My Collection",
    "owner": "abcdef",
    "created": 1328569452.406,
    "last_modified": 1328569492.406,
    "item_tiids": ["origtiid1", "origtiid2"] 
    }

ALIAS_DATA = {
    "title":["Why Most Published Research Findings Are False"],
    "url":["http://www.plosmedicine.org/article/info:doi/10.1371/journal.pmed.0020124"],
    "doi": ["10.1371/journal.pmed.0020124"],
    "created": 12345.111,
    "last_modified": 12346.222,
    }

ALIAS_CANONICAL_DATA = {
    "title":["Why Most Published Research Findings Are False"],
    "url":["http://www.plosmedicine.org/article/info:doi/10.1371/journal.pmed.0020124"],
    "doi": ["10.1371/journal.pmed.0020124"],
    "created": 12387239847.234,
    "last_modified": 1328569492.406
    }


STATIC_META = {
        "display_name": "readers",
        "provider": "Mendeley",
        "provider_url": "http://www.mendeley.com/",
        "description": "Mendeley readers: the number of readers of the article",
        "icon": "http://www.mendeley.com/favicon.ico",
        "category": "bookmark",
        "can_use_commercially": "0",
        "can_embed": "1",
        "can_aggregate": "1",
        "other_terms_of_use": "Must show logo and say 'Powered by Santa'",
        }

KEY1 = "8888888888.8"
KEY2 = "9999999999.9"
VAL1 = 1
VAL2 = 2

METRICS_DATA = {
    "ignore": False,
    "static_meta": STATIC_META,
    "provenance_url": ["http://api.mendeley.com/research/public-chemical-compound-databases/"],
    "values":{
        KEY1: VAL1,
        KEY2: VAL2
    }
}

METRICS_DATA2 = {
    "ignore": False,
    "latest_value": 21,
    "static_meta": STATIC_META,
    "provenance_url": ["http://api.mendeley.com/research/public-chemical-compound-databases/"],
    "values":{
        KEY1: VAL1,
        KEY2: VAL2
    }
} 

METRICS_DATA3 = {
    "ignore": False,
    "latest_value": 31,
    "static_meta": STATIC_META,
    "provenance_url": ["http://api.mendeley.com/research/public-chemical-compound-databases/"],
    "values":{
        KEY1: VAL1,
        KEY2: VAL2
    }
}

METRIC_NAMES = ["foo:views", "bar:views", "bar:downloads", "baz:sparkles"]


BIBLIO_DATA = {
        "title": "An extension of de Finetti's theorem", 
        "journal": "Advances in Applied Probability", 
        "author": [
            "Pitman, J"
            ], 
        "collection": "pitnoid", 
        "volume": "10", 
        "id": "p78",
        "year": "1978",
        "pages": "268 to 270"
    }


ITEM_DATA = {
    "_id": "123",
    "_rev": "456",
    "created": 1330260456.916,
    "last_modified": 12414214.234,
    "aliases": ALIAS_DATA,
    "metrics": { 
        "wikipedia:mentions": METRICS_DATA,
        "bar:views": METRICS_DATA2
    },
    "biblio": BIBLIO_DATA
}

TEST_PROVIDER_CONFIG = {
    "wikipedia": {}
}

TEST_DB_NAME = "test_models"


class TestSaveable():
    def setUp(self):
        pass

    def test_id_gets_set(self):
        s = models.Saveable(dao="dao")
        assert_equals(len(s.id), 32)

        s2 = models.Saveable(dao="dao", id="123")
        assert_equals(s2.id, "123")

    def test_as_dict(self):
        s = models.Saveable(dao="dao")
        s.foo = "a var"
        s.bar = "another var"
        assert_equals(s.as_dict()['foo'], "a var")

    def test_as_dict_recursive(self):
        s = models.Saveable(dao="dao")
        class TestObj:
            pass
        
        foo =  TestObj()
        foo.bar = "I'm in foo!"

        s.constituent_dict = {}
        s.constituent_dict["foo_obj"] = foo

        assert_equals(s.as_dict()['constituent_dict']['foo_obj']['bar'], foo.bar)



class TestItemFactory():

    def setUp(self): 
        self.d = MockDao()

    def test_make_new(self):
        '''create an item from scratch.'''
        item = models.ItemFactory.make_simple(self.d)
        assert_equals(len(item.id), 32)
        assert item.created < datetime.datetime.now().isoformat()
        assert_equals(item.aliases.__class__.__name__, "Aliases")

    def test_adds_genre(self):
        self.d.setResponses([deepcopy(ITEM_DATA)])
        item = models.ItemFactory.build_item(deepcopy(ITEM_DATA), [])
        assert_equals(item["biblio"]['genre'], "article")

    def test_get_metric_names(self):
        response = models.ItemFactory.get_metric_names(TEST_PROVIDER_CONFIG)
        assert_equals(response, ['wikipedia:mentions'])

    def test_decide_genre_article_doi(self):
        aliases = {"doi":["10:123", "10:456"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "article")

    def test_decide_genre_article_pmid(self):
        aliases = {"pmid":["12345678"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "article")

    def test_decide_genre_slides(self):
        aliases = {"url":["http://www.slideshare.net/jason/my-slides"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "slides")

    def test_decide_genre_software(self):
        aliases = {"url":["http://www.github.com/jasonpriem/my-sofware"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "software")

    def test_decide_genre_dataset(self):
        aliases = {"doi":["10.5061/dryad.18"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "dataset")

    def test_decide_genre_webpage(self):
        aliases = {"url":["http://www.google.com"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "webpage")

    def test_decide_genre_unknown(self):
        aliases = {"unknown_namespace":["myname"]}
        genre = models.ItemFactory.decide_genre(aliases)
        assert_equals(genre, "unknown")




class TestItem():

    def setUp(self):
        self.d = MockDao()
        self.d.setResponses([deepcopy(ITEM_DATA)])


    def test_mock_dao(self):
        assert_equals(self.d.get("123"), ITEM_DATA)

    def ITEM_DATA_init(self):
        i = models.Item(self.d)
        assert_equals(len(i.id), 32) # made a uuid, yay

    def ITEM_DATA_save(self):
        i = models.Item(self.d, id="123")

        # load all the values from the item_DATA into the test item.
        for key in ITEM_DATA:
            setattr(i, key, ITEM_DATA[key])
        i.save()

        assert_equals(i.aliases, ALIAS_DATA)

        seed = deepcopy(ITEM_DATA)
        seed["_id"] = "123"
        # the fake dao puts the doc-to-save in the self.input var.
        assert_equals(self.input, seed)

class TestCollectionFactory():

    def setUp(self):        
        self.d = MockDao()
        
    def COLLECTION_DATA_load(self):
        self.d.get = lambda id: deepcopy(COLLECTION_DATA)
        c = models.Collection(self.d, id="SomeCollectionId")
        c.load()
        assert_equals(c.collection_name, "My Collection")
        assert_equals(c.item_ids(), [u'origtiid1', u'origtiid2'])

    @raises(LookupError)
    def test_load_with_nonexistant_collection_fails(self):
        self.d.setResponses([None])
        factory = models.CollectionFactory.make(self.d, "AnUnknownCollectionId")

    def test_creates_identifier(self):
        coll = models.CollectionFactory.make(self.d)
        assert_equals(len(coll.id), 6)


class TestCollection():

    def setUp(self):        
        self.d = MockDao()

    def test_mock_dao(self):
        self.d.setResponses([ deepcopy(COLLECTION_DATA)])
        assert_equals(self.d.get("SomeCollectionId"), COLLECTION_DATA)

    def COLLECTION_DATA_init(self):
        c = models.Collection(self.d)
        assert_equals(len(c.id), 32) # made a uuid, yay

    def COLLECTION_DATA_add_items(self):
        c = models.Collection(self.d, seed=deepcopy(COLLECTION_DATA))
        c.add_items(["newtiid1", "newtiid2"])
        assert_equals(c.item_ids(), [u'origtiid1', u'origtiid2', 'newtiid1', 'newtiid2'])

    def COLLECTION_DATA_remove_item(self):
        c = models.Collection(self.d, seed=deepcopy(COLLECTION_DATA))
        c.remove_item("origtiid1")
        assert_equals(c.item_ids(), ["origtiid2"])

    def COLLECTION_DATA_save(self):
        # this fake save method puts the doc-to-save in the self.input variable
        def fake_save(data, id):
            self.input = data
        self.d.update_item = fake_save

        c = models.Collection(self.d)

        # load all the values from the item_DATA into the test item.
        for key in COLLECTION_DATA:
            setattr(c, key, COLLECTION_DATA[key])
        c.save()

        seed = deepcopy(COLLECTION_DATA)
        # the dao changes the contents to give the id variable the leading underscore expected by couch
        seed["_id"] = seed["id"]
        del(seed["id"])

        # check to see if the fake save method did in fact "save" the collection as expected
        assert_equals(self.input, seed)

    def test_collection_delete(self):
        self.d.delete = lambda id: True
        c = models.Collection(self.d, id="SomeCollectionId")
        response = c.delete()
        assert_equals(response, True)

class TestBiblio(unittest.TestCase):
    pass

class TestAliases(unittest.TestCase):

    def setUp(self):
        pass
        
    def tearDown(self):
        pass 

    def test_init(self):
        a = models.Aliases()
        a = models.Aliases()

        a = models.Aliases(seed=ALIAS_DATA)
        assert a.title == ["Why Most Published Research Findings Are False"]

      
    def test_add(self):
        a = models.Aliases()
        a.add_alias("foo", "id1")
        a.add_alias("foo", "id2")
        a.add_alias("bar", "id1")

        assert a.last_modified < datetime.datetime.now().isoformat()
        
        # check the data structure is correct
        expected = {"foo":["id1", "id2"], "bar":["id1"]}
        del a.last_modified, a.created
        assert a.__dict__ == expected, a

    def test_add_unique(self):
        a = models.Aliases()
        a.add_alias("foo", "id1")
        a.add_alias("foo", "id2")
        a.add_alias("bar", "id1")

        to_add = [
            ("baz", "id1"),
            ("baz", "id2"),
            ("foo", "id3"),
            ("bar", "id1")
        ]
        a.add_unique(to_add)
        
        # check the data structure is correct
        expected = {"foo":["id1", "id2", "id3"], 
                    "bar":["id1"], 
                    "baz" : ["id1", "id2"]}
        del a.last_modified, a.created
        assert_equals(a.__dict__, expected)

        
    def test_add_potential_errors(self):
        # checking for the string/list type bug
        a = models.Aliases()
        a.doi = ["error"]
        a.add_alias("doi", "noterror")
        assert_equals(a.doi, ["error", "noterror"])
        
    def test_single_namespaces(self):
        a = models.Aliases(seed=ALIAS_DATA)
        
        assert a.doi == ["10.1371/journal.pmed.0020124"]
        assert a.url == ["http://www.plosmedicine.org/article/info:doi/10.1371/journal.pmed.0020124"]

        assert_equals(len(a.get_aliases_list()), 3)
        
        aliases = a.get_aliases_list("doi")
        assert aliases == [("doi", "10.1371/journal.pmed.0020124")], aliases
        
        aliases = a.get_aliases_list("title")
        assert aliases == [("title", "Why Most Published Research Findings Are False")]

    @raises(AttributeError)
    def test_missing(self):
        a = models.Aliases(seed=ALIAS_DATA)
        
        failres = a.my_missing_namespace
        assert failres == [], failres
        
    def test_multi_namespaces(self):
        a = models.Aliases(seed=ALIAS_DATA)
        
        ids = a.get_aliases_list(["doi", "url"])
        assert ids == [("doi", "10.1371/journal.pmed.0020124"),
                        ("url", "http://www.plosmedicine.org/article/info:doi/10.1371/journal.pmed.0020124")], ids
    
    def test_dict(self):
        a = models.Aliases(seed=ALIAS_DATA)
        assert a.as_dict() == ALIAS_DATA



    

        
        
        
