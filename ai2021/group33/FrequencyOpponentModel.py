from typing import NewType, cast, Dict, List, Set, Collection
from decimal import *
from __future__ import annotations

from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.progress.Progress import Progress


# Frequency Opponent Model
class FrequencyOpponentModel(UtilitySpace):
    __DECIMALS = '0.0001'; # rounding accuracy

    def __init__(self, *args) -> None:
        '''
        Constructor. Assumes given frequency dictionary is equal to the available issues
        Args:
            domain (Domain)                      : the domain (duh)
            freqs  (Dict[str, Dict[Value, int]]) : observed frequencies for all issues.
            total  (Decimal)                     : total number of bids contained in freqs.  
                                                   This is assumed to be equal to the sum of 
                                                   integer values in (freqs) for each issue.
            resBid (Bid)                         : Reservation bid. Can be None.
        '''
        super().__init__()
        self.domain = None
        self.bidFrequencies = None
        self.totalBids = Decimal(0)
        self.resBid = None
        if len(args) == 4:
            if isinstance(args[0], Domain) and isinstance(args[1], Dict[str, Dict[Value, int]]) and \
               isinstance(args[2], Decimal) and isinstance(args[3], Bid):
                if args[0] is None:
                    raise NotImplementedError("Given domain is not initialized.")
            self.domain = args[0]
            self.bidFrequencies = args[1]
            self.totalBids = args[2]
            self.resBid = args[3]

    def __hash__(self) -> int:
        prime = 31
        result = 1
        result = result * prime + (0 if (self.bidFrequencies is None) else self.bidFrequencies.__hash__)
        result = result * prime + (0 if (self.domain is None) else self.domain.__hash__)
        result = result * prime + (0 if (self.totalBids is None) else self.totalBids.__hash__)
        return result

    def __repr__(self) -> str:
        return "FrequencyOpponentModel[" + self.totalBids + "," + self.bidFrequencies + "]"

    def __eq__(self, o: FrequencyOpponentModel) -> bool:
        if self == o:
            return True
        if o is None or type(self) != type(o):
            return False
        if self.bidFrequencies is None: 
            if o.bidFrequencies is not None :
                return False
        elif o.bidFrequencies != self.bidFrequencies:
            return False
        if self.domain is None: 
            if o.domain is not None:
                return False
        elif o.domain != self.domain:
            return False
        if self.totalBids is None:
            if o.totalBids is not None:
                return False
        elif o.totalBids != self.totalBids:
            return False
        return True
        


    def withDomain(self, newDomain:Domain, newResBid:Bid) -> FrequencyOpponentModel:
        '''
        Initializes the model. Must be called first after constructing an instance.
        Can be called again later subject to changes to its parameters.
        '''
        if newDomain is None:
            raise NotImplementedError("Given domain is not initialized.")
        # TODO Should debug here later, also maybe use available frequencies in some way
        return FrequencyOpponentModel(newDomain, dict.fromkeys(list(newDomain.getIssues()), Dict[Value, int]), Decimal(0), newResBid)
    

    def withAction(self, action:Action, progress:Progress) -> FrequencyOpponentModel:
        '''
        Update this with a new action that was done by the opponent. 
        withDomain must be called before this
        '''
        if self.domain is None:
            raise NotImplementedError("Given domain is not initialized.")
        if not isinstance(action, Offer):
            return self
        bid = action.getBid()
        newFreqs = self.cloneDict(self.bidFrequencies)
        for issue in self.domain.getIssues():
            freqs = newFreqs[issue]
            value = bid.getValue(issue)
            if value is not None:
                oldfreq = freqs[value]
                if oldfreq is None:
                    oldfreq = 0
                freqs[value] = oldfreq + 1
        return FrequencyOpponentModel(self.domain, newFreqs, self.totalBids + Decimal(1), self.resBid)


    def getCounts(self, issue:str) -> Dict[Value, int]:
        '''
        @param issue(Str): issue to get the frequency of
        @return (Dict[Value, int]): Dictionary of values and number of times they were used in previous bids.
        '''
        if self.domain is None:
            raise NotImplementedError("Given domain is not initialized.")
        if issue not in self.bidFrequencies:
            return Dict(None, 0)
        return self.bidFrequencies[issue]


    def getFraction(self, issue:str, value:Value) -> Decimal:
        if self.totalBids == Decimal(0):
            return Decimal(1)
        freq = self.bidFrequencies[issue][value]
        # TODO can freqs be None??
        if freq is None:
            freq = 0
        return Decimal(freq) / Decimal(len(self.bidFrequencies)).quantize(FrequencyOpponentModel.__DECIMALS, rounding=ROUND_HALF_UP)


    def getUtility(self, bid:Bid ) -> Decimal:
        if self.domain is None:
            raise NotImplementedError("Given domain is not initialized.")
        if self.totalBids == Decimal(0):
            return Decimal(1)
        sum = Decimal(0)
        # Assume all issues have equal weight (might change it later)
        for issue in self.domain.getIssues():
            if issue in bid.getIssues():
                sum += self.getFraction(issue, bid.getValue(issue))
        return sum / self.totalBids.quantize(FrequencyOpponentModel.__DECIMALS, rounding=ROUND_HALF_UP)


    def cloneDict(self, freqs:Dict[str, Dict[Value, int]]) -> Dict[str, Dict[Value, int]]:
        newDict = {}
        for issue in freqs.keys:
            newDict2 = {}
            for value in freqs[issue].keys:
                newDict2[value] = freqs[issue][value]
            newDict[issue] = newDict2
        return newDict

    def getName(self) -> str:
        if self.domain is None:
            raise NotImplementedError("Given domain is not initialized.")
        return "Frequency Opponent Model " + self.__hash__ + " For " + self.domain
    
    def getDomain(self) -> Domain:
        return self.domain
    
    def getReservationBid(self) -> Bid:
        return self.resBid
