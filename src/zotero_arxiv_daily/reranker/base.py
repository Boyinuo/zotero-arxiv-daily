from abc import ABC, abstractmethod
from omegaconf import DictConfig
from ..protocol import Paper, CorpusPaper
from .interest_profile import weighted_corpus
import numpy as np
from typing import Type
class BaseReranker(ABC):
    def __init__(self, config:DictConfig):
        self.config = config

    def compute_scores(self, candidates:list[Paper], corpus:list[CorpusPaper]) -> np.ndarray:
        corpus, corpus_weight = weighted_corpus(corpus, self.config)
        sim = self.get_similarity_score(
            [c.title + " " + c.abstract for c in candidates],
            [c.title + " " + c.abstract for c in corpus],
        )
        assert sim.shape == (len(candidates), len(corpus))
        return (sim * corpus_weight).sum(axis=1) * 10 # [n_candidate]

    def rerank(self, candidates:list[Paper], corpus:list[CorpusPaper]) -> list[Paper]:
        scores = self.compute_scores(candidates, corpus)
        for s,c in zip(scores,candidates):
            c.score = float(s)
        candidates = sorted(candidates,key=lambda x: x.score,reverse=True)
        return candidates
    
    @abstractmethod
    def get_similarity_score(self, s1:list[str], s2:list[str]) -> np.ndarray:
        raise NotImplementedError

registered_rerankers = {}

def register_reranker(name:str):
    def decorator(cls):
        registered_rerankers[name] = cls
        return cls
    return decorator

def get_reranker_cls(name:str) -> Type[BaseReranker]:
    if name not in registered_rerankers:
        raise ValueError(f"Reranker {name} not found")
    return registered_rerankers[name]
