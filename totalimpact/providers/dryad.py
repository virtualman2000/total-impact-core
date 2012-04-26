import time, re, urllib
from totalimpact.providers.provider import Provider, ProviderError, ProviderTimeout,ProviderServerError, ProviderClientError, ProviderHttpError, ProviderState, ProviderContentMalformedError, ProviderValidationFailedError
from totalimpact.models import Aliases, Biblio
from xml.dom import minidom 

import requests
import simplejson

from totalimpact.tilogging import logging
logger = logging.getLogger(__name__)

class Dryad(Provider):  

    def __init__(self, config):
        super(Dryad, self).__init__(config)
        self.state = DryadState(config)
        self.id = self.config.id
        
        self.dryad_doi_rx = re.compile(r"(10\.5061/.*)")
        self.member_items_rx = re.compile(r"(10\.5061/.*)</span")

        self.DRYAD_VIEWS_PACKAGE_PATTERN = re.compile("(?P<views>\d+)\W*views<span", re.DOTALL)
        self.DRYAD_DOWNLOADS_PATTERN = re.compile("(?P<downloads>\d+)\W*downloads</span", re.DOTALL)

    def _is_dryad_doi(self, doi):
        response = self.dryad_doi_rx.search(doi)
        return response is not None

    def _is_relevant_id(self, alias):
        return self._is_dryad_doi(alias[1])
    
    def _get_named_arr_int_from_xml(self, xml, name, is_expected=True):
        """ Find the first node in the XML <arr> sections which are of node type <int>
            and return their text values. """
        identifiers = []
        arrs = self._get_named_arrs_from_xml(xml, name, is_expected)
        for arr in arrs:
            node = arr.getElementsByTagName('int')[0]
            identifiers.append(node.firstChild.nodeValue)
        return identifiers

    def _get_named_arr_str_from_xml(self, xml, name, is_expected=True):
        """ Find the first node in the XML <arr> sections which are of node type <str>
            and return their text values. """
        identifiers = []
        arrs = self._get_named_arrs_from_xml(xml, name, is_expected)
        for arr in arrs:
            node = arr.getElementsByTagName('str')[0]
            identifiers.append(node.firstChild.nodeValue)
        return identifiers

    def _get_named_arrs_from_xml(self, xml, name, is_expected=True):
        """ Find <arr> sections in the given xml document which have a
            match for the name attribute """
        try:
            doc = minidom.parseString(xml)
        except minidom.ExpatError, e:
            raise ProviderContentMalformedError("Content parse provider supplied XML document")
        arrs = doc.getElementsByTagName('arr')
        matching_arrs = [elem for elem in arrs if elem.attributes['name'].value == name]
        if (is_expected and (len(matching_arrs) == 0)):
            raise ProviderContentMalformedError("Did not find expected number of matching arr blocks")
        return matching_arrs

    def member_items(self, query_string, query_type):
        enc = urllib.quote(query_string)

        url = self.config.member_items["querytype"]["dryad_author"]['url'] % enc
        logger.debug(self.config.id + ": query type " + query_type)
        logger.debug(self.config.id + ": attempting to retrieve member items from " + url)
        
        # try to get a response from the data provider        
        response = self.http_get(url, 
            timeout=self.config.member_items.get('timeout', None))

        if response.status_code != 200:
            if response.status_code >= 500:
                raise ProviderServerError(response)
            else:
                raise ProviderClientError(response)

        # did we get a page back that seems mostly valid?
        if ("response" not in response.text):
            raise ProviderContentMalformedError("Content does not contain expected text")

        identifiers = self._get_named_arr_str_from_xml(response.text, "dc.identifier", is_expected=False)

        return [("doi", hit.replace("doi:", "")) for hit in list(set(identifiers))]

    
    def aliases(self, item):
        # get the alias object
        alias_object = item.aliases
        logger.info(self.config.id + ": aliases requested for tiid:" + item.id)
        
        # Get a list of the new aliases that can be discovered from the data
        # source
        new_aliases = []
        for alias in alias_object.get_aliases_list("doi"):
            if not self._is_dryad_doi(alias[1]):
                continue
            logger.debug(self.config.id + ": processing aliases for tiid:" + item.id)
            id = alias[1]
            new_aliases += self.get_aliases_for_id(id)
        
        # update the original alias object with new unique aliases
        alias_object.add_unique(new_aliases)
        
        # log our success
        logger.debug(self.config.id + ": discovered aliases for tiid " + item.id + ": " + str(new_aliases))
        logger.info(self.config.id + ": aliases completed for tiid:" + item.id)
        
        # no need to set the aliases on the item, as everything is by-reference
        return item
        

    def get_aliases_for_id(self, id):
        url = self.config.aliases['url'] % id
        logger.debug(self.config.id + ": attempting to retrieve aliases from " + url)

        # try to get a response from the data provider        
        response = self.http_get(url, 
            timeout=self.config.aliases.get('timeout', None))
        
        # register the hit, mostly so that anyone copying this remembers to do it,
        # - we have overriden this in the DryadState object, so it doesn't do anything
        self.state.register_unthrottled_hit()
        
        # FIXME: we have to observe the Dryad interface for a bit to get a handle
        # on these response types - this is just a default approach...
        if response.status_code != 200:
            if response.status_code >= 500:
                raise ProviderServerError(response)
            else:
                raise ProviderClientError(response)

        # did we get a page back that seems mostly valid?
        if ("response" not in response.text):
            raise ProviderContentMalformedError("Content does not contain expected text")
        
        # extract the aliases
        new_aliases = self._extract_aliases(response.text)
        if new_aliases is not None:
            logger.debug(self.config.id + ": found aliases: " + str(new_aliases))
            return new_aliases
        return []


    def _extract_aliases(self, xml):
        identifiers = []
        url_identifiers = self._get_named_arr_str_from_xml(xml, u'dc.identifier.uri')
        identifiers += [("url", url) for url in url_identifiers]

        title_identifiers = self._get_named_arr_str_from_xml(xml, u'dc.title')
        identifiers += [("title", title) for title in title_identifiers]

        return identifiers

    def provides_metrics(self): 
        return True
    
    def get_show_details_url(self, doi):
        return "http://dx.doi.org/" + doi

    def _get_dryad_doi(self, item):
        try:
            for doi in item.aliases.doi:
                if self._is_dryad_doi(doi):
                    return doi
        except (AttributeError, KeyError):
            return None

    def metrics(self, item):
        id = self._get_dryad_doi(item)
        if id is not None:
            new_metrics = self._get_metrics_for_id(id)
            item.metrics = self._update_metrics_from_dict(new_metrics, item.metrics)
        else:
            new_metrics = {
                "dryad:package_views": None,
                "dryad:total_downloads": None,
                "dryad:most_downloaded_file": None
            }
            item.metrics = self._update_metrics_from_dict(new_metrics, item.metrics)

        logger.info("{0}: metrics completed for tiid {1}".format(self.config.id, item.id))
        return item


    def _get_metrics_for_id(self, id):
        url = self.config.metrics['url'] % id
        logger.debug(self.config.id + ": attempting to retrieve metrics from " + url)
        
        # try to get a response from the data provider        
        response = self.http_get(url, 
            timeout=self.config.metrics.get('timeout', None))

        # register the hit, mostly so that anyone copying this remembers to do it,
        # - we have overriden this in the DryadState object, so it doesn't do anything
        self.state.register_unthrottled_hit()
        
        # FIXME: we have to observe the Dryad interface for a bit to get a handle
        # on these response types - this is just a default approach...
        if response.status_code != 200:
            if response.status_code >= 500:
                raise ProviderServerError(response)
            else:
                raise ProviderClientError(response)
        
        # did we get a page back that seems mostly valid?
        if ("Dryad" not in response.text):
            raise ProviderContentMalformedError("Content does not contain expected text")

        # extract the aliases
        return self._extract_stats(response.text)


    def _extract_stats(self, content):
        view_matches_package = self.DRYAD_VIEWS_PACKAGE_PATTERN.search(content)
        try:
            view_package = view_matches_package.group("views")
        except ValueError:
            raise ProviderContentMalformedError("Content does not contain expected text")
        
        download_matches = self.DRYAD_DOWNLOADS_PATTERN.finditer(content)
        try:
            downloads = [int(download_match.group("downloads")) for download_match in download_matches]
            total_downloads = sum(downloads)
            max_downloads = max(downloads)
        except ValueError:
            raise ProviderClientError(content)            

        return {
            "dryad:package_views": int(view_package),
            "dryad:total_downloads": int(total_downloads),
            "dryad:most_downloaded_file": int(max_downloads)
        }



    def provides_biblio(self): 
        return True

    def biblio(self, item): 
        id = self._get_dryad_doi(item)
        # Only lookup biblio for items with dryad doi's
        if id:
            biblio_object = self.get_biblio_for_id(id)
            item.biblio = biblio_object
        else:
            logger.debug(self.config.id + ": Not checking biblio for %s as no dryad doi" % item.id)
        return item

    def get_biblio_for_id(self, id):
        url = self.config.biblio['url'] % id
        logger.debug(self.config.id + ": attempting to retrieve biblio from " + url)
        
        # try to get a response from the data provider        
        response = self.http_get(url, 
            timeout=self.config.biblio.get('timeout', None))
        
        # register the hit, mostly so that anyone copying this remembers to do it,
        # - we have overriden this in the DryadState object, so it doesn't do anything
        self.state.register_unthrottled_hit()
        
        # FIXME: we have to observe the Dryad interface for a bit to get a handle
        # on these response types - this is just a default approach...
        if response.status_code != 200:
            if response.status_code >= 500:
                raise ProviderServerError(response)
            else:
                raise ProviderClientError(response)
        
        # extract the aliases
        bibJSON = self._extract_biblio(response.text)
        biblio_object = Biblio(bibJSON)

        return biblio_object


    def _extract_biblio(self, xml):
        biblio_dict = {}

        try:
            title = self._get_named_arr_str_from_xml(xml, 'dc.title_ac')
            biblio_dict["title"] = title[0]
        except AttributeError:
            raise ProviderContentMalformedError("Content does not contain expected text")

        try:
            year = self._get_named_arr_int_from_xml(xml, 'dc.date.accessioned.year')
            biblio_dict["year"] = year[0]
        except AttributeError:
            raise ProviderContentMalformedError("Content does not contain expected text")

        return biblio_dict


class DryadState(ProviderState):
    def __init__(self, config):
        # need to init the ProviderState object counter
        if config.rate is not None:        
            super(DryadState, self).__init__(config.rate['period'], config['limit'])
        else:
            super(DryadState, self).__init__(throttled=False)
            
    def register_unthrottled_hit(self):
        # override this method, so it has no actual effect
        pass
        
  


