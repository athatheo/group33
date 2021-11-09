import logging
from random import randint
import traceback
from typing import cast, Dict, List, Set, Collection

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.LearningDone import LearningDone
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.Vote import Vote
from geniusweb.actions.Votes import Votes
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.OptIn import OptIn
from geniusweb.inform.Settings import Settings
from geniusweb.inform.Voting import Voting
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.utils import val


class Group33Party(DefaultParty):
    """
    Offers random bids until a bid with sufficient utility is offered.
    """
    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO,"party is initialized")
        self._profile = None
        self._lastReceivedBid:Bid = None

        # Acceptance Strategy params
        self.highTime = 0.99
        self.bidsBuffer = []
        self.tempFlag = False

    # Override
    def notifyChange(self, info: Inform):
        #self.getReporter().log(logging.INFO,"received info:"+str(info))
        if isinstance(info,Settings) :
            self._settings:Settings=cast(Settings,info)    
            self._me = self._settings.getID()
            self._protocol:str = str(self._settings.getProtocol().getURI())
            self._progress = self._settings.getProgress()
            if "Learn" ==  self._protocol:
                self.getConnection().send(LearningDone(self._me)) #type:ignore
            else:
                self._profile = ProfileConnectionFactory.create(info.getProfile().getURI(), self.getReporter())
        elif isinstance(info, ActionDone):
            action:Action=cast( ActionDone,info).getAction()
            if isinstance(action, Offer):
                self._lastReceivedBid = cast(Offer, action).getBid()
                self.bidsBuffer.append(self._lastReceivedBid)
        elif isinstance(info, YourTurn):
            self._myTurn()
            if isinstance(self._progress, ProgressRounds) :
                self._progress = self._progress.advance()
        elif isinstance(info, Finished):
            self.terminate()
        elif isinstance(info, Voting):
            # MOPAC protocol
            self._lastvotes = self._vote(cast(Voting, info));
            val(self.getConnection()).send(self._lastvotes)
        elif isinstance(info, OptIn):
            val(self.getConnection()).send(self._lastvotes)
        else:
            self.getReporter().log(logging.WARNING, "Ignoring unknown info "+str(info))


    # Override
    def getCapabilities(self) -> Capabilities:
        return Capabilities( set([ "SAOP", "Learn", "MOPAC"]), set(['geniusweb.profile.utilityspace.LinearAdditive']))

    # Override
    def getDescription(self) -> str:
        return "Offers random bids until a bid with sufficient utility is offered. Parameters minPower and maxPower can be used to control voting behaviour."

    # Override
    def terminate(self):
        self.getReporter().log(logging.INFO,"party is terminating:")
        super().terminate()
        if self._profile != None:
            self._profile.close()
            self._profile = None


    def _myTurn(self):
        if self._isGood(self._lastReceivedBid):
            action = Accept(self._me, self._lastReceivedBid)
        else:
            for _attempt in range(20):
                bid = self._getBid(self._profile.getProfile().getDomain())
                if self._isGood(bid):
                    break
            action = Offer(self._me, bid)
        self.getConnection().send(action)

    def _isGood(self, bid:Bid, party=None)->bool:
        if bid == None:
            return False
        profile = self._profile.getProfile()
        if isinstance(profile, UtilitySpace):
            curProgress = self._progress.getCurrentRound() -1
            totalDuration = self._progress.getDuration() - 1
            if curProgress < 0.5*totalDuration:
                # Use next criterion
                # TODO: Change the way of calculating the nextBid, based on the Bidding Strategy
                nextBid = self._getBid(self._profile.getProfile().getDomain())
                return profile.getUtility(bid) >= profile.getUtility(nextBid)
            if curProgress >= 0.5*totalDuration:
                # Use combi criterion
                # TODO: Change the way of calculating the nextBid, based on the Bidding Strategy
                nextBid = self._getBid(self._profile.getProfile().getDomain())
                ac_next = profile.getUtility(bid) >= profile.getUtility(nextBid)
                ac_time = curProgress >= self.highTime
                utils = []
                windowStart = curProgress - (totalDuration - curProgress)
                windowEnd = curProgress + 1
                for bids in self.bidsBuffer[windowStart:windowEnd]:
                    for oneBid in [bids]: # Assuming that in each time step, there will be
                        # multiple bids
                        utils.append(profile.getUtility(oneBid))
                if len(utils) > 0:
                    if party == self.powerParty[0] and len(self.powerParty) == 1: # If the party has
                        # the most power, get maximum
                        ac_combi = profile.getUtility(bid) >= max(utils)
                    else: # If the party doesnt have the most power, get the average
                        ac_combi = profile.getUtility(bid) >= sum(utils)/len(utils)
                    return (ac_next or ac_time) and ac_combi
                else:
                    return False
            #return profile.getUtility(bid) > 0.6
        raise Exception("Can not handle this type of profile")

    def _getBid(self, domain:Domain) -> Bid:
        allBids = AllBidsList(domain)
        max_util = -1
        max_bid = None
        profile = self._profile.getProfile()
        for bid in allBids:
            util = profile.getUtility(bid)
            if util > max_util:
                max_util = util
                max_bid = bid

        return max_bid
    
    def _vote(self, voting:Voting) ->Votes :
        '''
        @param voting the {@link Voting} object containing the options
        
        @return our next Votes.
        '''
        val = self._settings.getParameters().get("minPower");
        # TODO - This should be set to the minimum power in order for a government to form
        minpower:int = val if isinstance(val, int) else 2
        # TODO - This should be set to the total power of all parties
        val = self._settings.getParameters().get("maxPower");
        maxpower:int = val if isinstance(val,int) else  9999999;

        # Get the party with most power
        if self.tempFlag == False:
            self.tempFlag = True
        self.powers = voting.getPowers()
        self.powerParty = [key for key, value in self.powers.items() if value == max(
            self.powers.values())]

        votes:Set[Vote]  = set([Vote(self._me, offer.getBid(), minpower, maxpower)\
                for offer in voting.getOffers() if self._isGood(offer.getBid(),
                                                                party=offer.getActor()
                                                                )
                                ])
        return Votes(self._me, votes);
