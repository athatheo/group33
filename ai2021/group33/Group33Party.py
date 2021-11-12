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

from collections import deque

DEQUE_SIZE = 5

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
        self.max_util = 1
        self.max_bid = None
        self.utils = []
        self.bestBids = deque([])
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
        return Capabilities( set(["MOPAC"]), set(['geniusweb.profile.utilityspace.LinearAdditive']))

    # Override
    def getDescription(self) -> str:
        return "Offers varying bids, starting from the maximum utility, and gradually reducing " \
               "the target utility in order to secure an agreement. Uses a combined acceptance " \
               "criterions. Parameters minPower and maxPower can be used to control voting behaviour."

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
                nextBid = self._getBid(self._profile.getProfile().getDomain())
                return profile.getUtility(bid) >= profile.getUtility(nextBid)
            if curProgress >= 0.5*totalDuration:
                # Use combi criterion
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
        raise Exception("Can not handle this type of profile")

    def _getBid(self, domain:Domain) -> Bid:

        profile = self._profile.getProfile()
        # In the first run of the function, calculate and store all bids with their utilities
        if self.max_bid == None:
            # Get all bids
            self.allBids = AllBidsList(domain)
            # Calculate and store the utility of each bid
            for bid in self.allBids:
                self.utils.append(profile.getUtility(bid))

           # Find the order in which the bids are sorted
            self.order = [bid for _,bid in sorted(zip(self.utils,list(range(len(self.utils)))),
                                                        reverse=True)]
            # Sort the bids
            self.allBids_temp = []
            allBids_list =  list(self.allBids)
            for i in range(len(self.order)):
                self.allBids_temp.append(allBids_list[self.order[i]])
            self.utils.sort(reverse=True)
            self.allBids = self.allBids_temp
            # Get the maximum bid
            self.max_bid = self._get_max_bid(domain)

            # Initialize the bestBids deque
            for _ in range(DEQUE_SIZE):
                self.bestBids.append(self.max_bid)

        curProgress = self._progress.getCurrentRound() - 1
        totalDuration = self._progress.getDuration() - 1
        # If it's early in the negotiation just return max utility bid
        if curProgress < 0.09*totalDuration:
            return self.max_bid
        else:
            self.max_bid = self._get_bid_in_window(domain)
            return self.max_bid

    """
    Returns in a random fashion the best 5 bids according to their utility. 
    The best 5 bids deteriorate over time, since the best bid is removed and one that is worse is added, to allow
    conceding.
    """
    def _get_bid_in_window(self, domain:Domain) -> Bid:
        allBids = self.allBids
        max_util = -1
        max_bid = None
        profile = self._profile.getProfile()
        for idx, bid in enumerate(allBids):
            util = self.utils[idx]
            if util < self.max_util:
                max_util = util
                max_bid = bid
                self.allBids = self.allBids[idx+1:]
                self.utils = self.utils[idx+1:]
                break

        if max_bid is None:
            return self.bestBids[randint(0, 4)]

        self.max_util = max_util

        self.bestBids.popleft()
        self.bestBids.append(max_bid)
        self.getReporter().log(logging.INFO,profile.getUtility(max_bid))
        return self.bestBids[randint(0, 4)]

    """
    Returns the bid with maximum utility from the available bids
    """
    def _get_max_bid(self, domain:Domain) ->Bid:
        allBids = self.allBids
        max_util = -1
        max_bid = None
        for idx,bid in enumerate(allBids):
            util = self.utils[idx]
            if util > max_util:
                max_util = util
                max_bid = bid

        self.max_util = max_util
        return max_bid

    def _vote(self, voting:Voting) ->Votes :
        '''
        @param voting the {@link Voting} object containing the options
        
        @return our next Votes.
        '''
        val = self._settings.getParameters().get("minPower");
        minpower:int = val if isinstance(val, int) else 2
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
